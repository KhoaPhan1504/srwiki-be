from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, UserOut
from app.supabase_client import anon_client, admin_client
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    client = anon_client()
    try:
        result = client.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {"data": {"full_name": payload.full_name}},
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Registration failed") from exc

    user = result.user
    if user is None:
        raise HTTPException(status_code=400, detail="Registration failed")

    # When Supabase's "Confirm email" setting is on, GoTrue's anti-enumeration
    # protection answers a sign-up for an existing email with a 200 and a fake
    # user whose `identities` list is empty. That user was never created, so we
    # must not insert a profile for it or roll back by deleting its id.
    if not user.identities:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        admin_client().table("profiles").insert(
            {"id": user.id, "full_name": payload.full_name}
        ).execute()
    except Exception as exc:
        try:
            admin_client().auth.admin.delete_user(user.id)
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail="Registration failed while creating profile"
        ) from exc

    return {"id": user.id, "email": user.email}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    client = anon_client()
    try:
        result = client.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest):
    client = anon_client()
    try:
        result = client.auth.refresh_session(payload.refreshToken)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: dict = Depends(get_current_user)):
    return None
