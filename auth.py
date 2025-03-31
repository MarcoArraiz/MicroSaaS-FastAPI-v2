import os
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from jose import JWTError, jwt
from datetime import datetime, timedelta

# Carga variables del .env
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Serializer para generar tokens (recuperación de contraseña)
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Funciones para JWT (login)
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        if user_email is None:
            return None
        return user_email
    except JWTError:
        return None

# Funciones para recuperación de contraseña
def generate_reset_token(email):
    return serializer.dumps(email, salt="reset-password")

def verify_reset_token(token, expiration=3600):
    try:
        email = serializer.loads(token, salt="reset-password", max_age=expiration)
        return email
    except:
        return None
