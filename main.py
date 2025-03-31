from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine
import models, schemas, utils
from auth import create_access_token, verify_token, generate_reset_token, verify_reset_token
from email_validator import validate_email, EmailNotValidError
from collections import Counter
from datetime import datetime
from email_config import conf
from fastapi_mail import FastMail, MessageSchema, MessageType

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Dependencia para obtener sesión de base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependencia para verificar usuario autenticado
def get_current_user(access_token: str = Cookie(None), db: Session = Depends(get_db)):
    if access_token is None:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})

    user_email = verify_token(access_token)
    if user_email is None:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})

    user = db.query(models.Usuario).filter(models.Usuario.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})

    return user

# Rutas protegidas
@app.get("/", response_class=HTMLResponse)
def leer_pedidos(request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(get_current_user)):
    pedidos = db.query(models.Pedido).filter(models.Pedido.usuario_id == user.id).all()
    return templates.TemplateResponse("index.html", {"request": request, "pedidos": pedidos, "user": user})

@app.get("/crear", response_class=HTMLResponse)
def crear_form(request: Request, user: models.Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("crear.html", {"request": request, "user": user})

@app.post("/crear")
async def crear_pedido(
    cliente: str = Form(...),
    producto: str = Form(...),
    cantidad: int = Form(...),
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user)
):
    pedido = models.Pedido(
        cliente=cliente,
        producto=producto,
        cantidad=cantidad,
        usuario_id=user.id
    )
    db.add(pedido)
    db.commit()
    db.refresh(pedido)

    # Enviar email
    message = MessageSchema(
        subject="Pedido Creado Exitosamente",
        recipients=[user.email],
        body=f"Tu pedido '{producto}' para '{cliente}' fue creado exitosamente con cantidad {cantidad}.",
        subtype=MessageType.plain
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    return RedirectResponse("/", status_code=303)

# Registro de usuario
@app.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})

@app.post("/registro", response_class=HTMLResponse)
def crear_usuario(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        valid = validate_email(email)
        email = valid.email
    except EmailNotValidError:
        return templates.TemplateResponse("registro.html", {"request": request, "error": "Correo no válido"})

    usuario_existente = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if usuario_existente:
        return templates.TemplateResponse("registro.html", {"request": request, "error": "El correo ya está registrado."})

    hashed_password = utils.get_password_hash(password)
    nuevo_usuario = models.Usuario(email=email, hashed_password=hashed_password)
    db.add(nuevo_usuario)
    db.commit()

    return RedirectResponse("/login", status_code=303)

# Login
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not usuario or not utils.verify_password(password, usuario.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Correo o contraseña incorrectos."})

    access_token = create_access_token({"sub": usuario.email})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

# Logout
@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# Mostrar formulario para editar pedido
@app.get("/editar/{pedido_id}", response_class=HTMLResponse)
def editar_form(
    pedido_id: int, request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(get_current_user)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id, models.Pedido.usuario_id == user.id).first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return templates.TemplateResponse("editar.html", {"request": request, "pedido": pedido, "user": user})

# Manejo de formulario POST para editar pedido
@app.post("/editar/{pedido_id}")
async def editar_pedido(
    pedido_id: int,
    cliente: str = Form(...),
    producto: str = Form(...),
    cantidad: int = Form(...),
    estado: str = Form(...),
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id, models.Pedido.usuario_id == user.id).first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    pedido.cliente = cliente
    pedido.producto = producto
    pedido.cantidad = cantidad
    pedido.estado = estado
    db.commit()

    # Enviar email de actualización
    message = MessageSchema(
        subject="Pedido Actualizado",
        recipients=[user.email],
        body=f"Tu pedido '{producto}' fue actualizado correctamente al estado '{estado}'.",
        subtype=MessageType.plain
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    return RedirectResponse("/", status_code=303)

# Eliminar pedido
@app.get("/eliminar/{pedido_id}")
def eliminar_pedido(
    pedido_id: int, db: Session = Depends(get_db), user: models.Usuario = Depends(get_current_user)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id, models.Pedido.usuario_id == user.id).first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    db.delete(pedido)
    db.commit()

    return RedirectResponse("/", status_code=303)

@app.post("/cambiar-estado/{pedido_id}")
def cambiar_estado_pedido(
    pedido_id: int,
    estado: str = Form(...),
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id, models.Pedido.usuario_id == user.id).first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    pedido.estado = estado
    db.commit()

    return RedirectResponse("/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(get_current_user)):
    # Pedidos del usuario
    pedidos = db.query(models.Pedido).filter(models.Pedido.usuario_id == user.id).all()

    # Total pedidos
    total_pedidos = len(pedidos)

    # Pedidos por mes
    pedidos_mensuales = (
        db.query(func.strftime("%Y-%m", models.Pedido.fecha_creacion), func.count(models.Pedido.id))
        .filter(models.Pedido.usuario_id == user.id)
        .group_by(func.strftime("%Y-%m", models.Pedido.fecha_creacion))
        .all()
    )

    meses = [mes for mes, _ in pedidos_mensuales]
    cantidad_pedidos_mes = [cantidad for _, cantidad in pedidos_mensuales]

    # Productos más pedidos
    productos_contados = Counter([pedido.producto for pedido in pedidos])
    productos = list(productos_contados.keys())
    cantidad_productos = list(productos_contados.values())

    # Clientes frecuentes
    clientes_contados = Counter([pedido.cliente for pedido in pedidos])
    clientes = list(clientes_contados.keys())
    cantidad_clientes = list(clientes_contados.values())

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "total_pedidos": total_pedidos,
            "meses": meses,
            "cantidad_pedidos_mes": cantidad_pedidos_mes,
            "productos": productos,
            "cantidad_productos": cantidad_productos,
            "clientes": clientes,
            "cantidad_clientes": cantidad_clientes
        }
    )

@app.get("/perfil", response_class=HTMLResponse)
def perfil_usuario(request: Request, user: models.Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("perfil.html", {"request": request, "user": user})

@app.post("/perfil")
def actualizar_perfil(
    email: str = Form(...),
    password: str = Form(None),
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user)
):
    # Actualizar email
    user.email = email

    # Actualizar contraseña solo si se proporciona
    if password:
        user.hashed_password = utils.get_password_hash(password)

    db.commit()

    return RedirectResponse("/perfil", status_code=303)


# Página para solicitar recuperación de contraseña
@app.get("/recuperar", response_class=HTMLResponse)
def recuperar_form(request: Request):
    return templates.TemplateResponse("recuperar.html", {"request": request})

# Manejo de la solicitud para enviar enlace al correo
@app.post("/recuperar")
async def enviar_enlace_recuperacion(email: str = Form(...), db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if usuario:
        token = generate_reset_token(email)
        reset_link = f"http://localhost:8000/reset-password/{token}"
        
        # Enviar correo real
        message = MessageSchema(
            subject="Recuperación de Contraseña",
            recipients=[email],
            body=f"Hola, usa este enlace para restablecer tu contraseña: {reset_link}",
            subtype=MessageType.plain
        )
        fm = FastMail(conf)
        await fm.send_message(message)

    return RedirectResponse("/login", status_code=303)

# Página para establecer nueva contraseña
@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_form(token: str, request: Request):
    email = verify_reset_token(token)
    if not email:
        return HTMLResponse("Enlace inválido o expirado", status_code=400)
    
    return templates.TemplateResponse("nueva_contrasena.html", {"request": request, "token": token})

# Actualizar la contraseña
@app.post("/reset-password/{token}")
def reset_password(token: str, password: str = Form(...), db: Session = Depends(get_db)):
    email = verify_reset_token(token)
    if not email:
        return HTMLResponse("Enlace inválido o expirado", status_code=400)

    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    usuario.hashed_password = utils.get_password_hash(password)
    db.commit()

    return RedirectResponse("/login", status_code=303)
