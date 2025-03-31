from pydantic import BaseModel, EmailStr
from datetime import datetime

class PedidoBase(BaseModel):
    cliente: str
    producto: str
    cantidad: int

class PedidoCreate(PedidoBase):
    pass

class PedidoOut(PedidoBase):
    id: int
    estado: str
    fecha_creacion: datetime

    class Config:
        from_attributes = True


class UsuarioBase(BaseModel):
    email: EmailStr

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioOut(UsuarioBase):
    id: int
    fecha_registro: datetime

    class Config:
        from_attributes = True
