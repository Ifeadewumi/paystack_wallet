"""
Hypothesis strategies for generating test data for Paystack Wallet models.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional

from hypothesis import strategies as st, settings
from hypothesis.strategies import composite

# Configure Hypothesis settings for property-based tests
settings.register_profile("default", max_examples=100, deadline=None)
settings.load_profile("default")

from app.models import (
    User, Wallet, Transaction, ApiKey,
    TransactionStatus, TransactionType, ApiKeyPermissions
)


# --- Basic Data Strategies ---

@composite
def email_strategy(draw):
    """Generate valid email addresses."""
    username = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=3,
        max_size=20
    ).filter(lambda x: x and x[0].isalpha()))
    
    domain = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=3,
        max_size=15
    ).filter(lambda x: x and x[0].isalpha()))
    
    tld = draw(st.sampled_from(["com", "org", "net", "edu", "gov"]))
    
    return f"{username}@{domain}.{tld}"


@composite
def wallet_number_strategy(draw):
    """Generate valid wallet numbers (10 digits)."""
    return draw(st.text(
        alphabet="0123456789",
        min_size=10,
        max_size=10
    ))


@composite
def google_id_strategy(draw):
    """Generate Google ID strings."""
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=10,
        max_size=30
    ))


@composite
def name_strategy(draw):
    """Generate human names."""
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    
    first = draw(st.sampled_from(first_names))
    last = draw(st.sampled_from(last_names))
    
    return f"{first} {last}"


@composite
def api_key_name_strategy(draw):
    """Generate API key names."""
    prefixes = ["Production", "Development", "Testing", "Staging", "Mobile", "Web", "Service"]
    suffixes = ["API", "Key", "Access", "Token", "Client"]
    
    prefix = draw(st.sampled_from(prefixes))
    suffix = draw(st.sampled_from(suffixes))
    
    return f"{prefix} {suffix}"


@composite
def transaction_reference_strategy(draw, prefix: str):
    """Generate transaction references with given prefix."""
    # Use UUID hex for uniqueness
    unique_part = uuid.uuid4().hex
    return f"{prefix}_{unique_part}"


@composite
def api_key_strategy(draw):
    """Generate API key strings."""
    prefix = "sk_live"
    random_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=32,
        max_size=32
    ))
    return f"{prefix}_{random_part}"


# --- Model Strategies ---

@composite
def user_strategy(draw, 
                 email: Optional[str] = None,
                 google_id: Optional[str] = None,
                 name: Optional[str] = None):
    """Generate User model instances."""
    return User(
        id=uuid.uuid4(),
        email=email or draw(email_strategy()),
        name=name or draw(st.one_of(st.none(), name_strategy())),
        picture=draw(st.one_of(st.none(), st.text(min_size=10, max_size=100))),
        google_id=google_id or draw(google_id_strategy()),
        created_at=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )),
        updated_at=draw(st.one_of(st.none(), st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )))
    )


@composite
def wallet_strategy(draw,
                   user: Optional[User] = None,
                   wallet_number: Optional[str] = None,
                   balance: Optional[int] = None):
    """Generate Wallet model instances."""
    if user is None:
        user = draw(user_strategy())
    
    return Wallet(
        id=uuid.uuid4(),
        user_id=user.id,
        user=user,
        wallet_number=wallet_number or draw(wallet_number_strategy()),
        balance=balance if balance is not None else draw(st.integers(min_value=0, max_value=1000000)),
        created_at=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )),
        updated_at=draw(st.one_of(st.none(), st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )))
    )


@composite
def transaction_strategy(draw,
                        wallet: Optional[Wallet] = None,
                        user: Optional[User] = None,
                        transaction_type: Optional[TransactionType] = None,
                        status: Optional[TransactionStatus] = None,
                        amount: Optional[int] = None,
                        reference: Optional[str] = None):
    """Generate Transaction model instances."""
    if wallet is None:
        if user is None:
            user = draw(user_strategy())
        wallet = draw(wallet_strategy(user=user))
    
    if user is None:
        user = wallet.user
    
    tx_type = transaction_type or draw(st.sampled_from(list(TransactionType)))
    
    # Generate appropriate reference based on type
    if reference is None:
        if tx_type == TransactionType.DEPOSIT:
            reference = draw(transaction_reference_strategy("dep"))
        else:  # TRANSFER
            reference = draw(transaction_reference_strategy("xfer"))
    
    return Transaction(
        id=uuid.uuid4(),
        wallet_id=wallet.id,
        wallet=wallet,
        user_id=user.id,
        user=user,
        type=tx_type,
        amount=amount if amount is not None else draw(st.integers(min_value=1, max_value=100000)),
        status=status or draw(st.sampled_from(list(TransactionStatus))),
        reference=reference,
        description=draw(st.one_of(st.none(), st.text(min_size=5, max_size=100))),
        authorization_url=draw(st.one_of(st.none(), st.text(min_size=10, max_size=200))),
        paid_at=draw(st.one_of(st.none(), st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        ))),
        created_at=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )),
        updated_at=draw(st.one_of(st.none(), st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )))
    )


@composite
def api_key_strategy_model(draw,
                          user: Optional[User] = None,
                          name: Optional[str] = None,
                          permissions: Optional[list] = None,
                          is_active: Optional[bool] = None,
                          expires_at: Optional[datetime] = None):
    """Generate ApiKey model instances."""
    if user is None:
        user = draw(user_strategy())
    
    if permissions is None:
        # Generate a non-empty subset of permissions
        all_permissions = list(ApiKeyPermissions)
        permissions = draw(st.lists(
            st.sampled_from(all_permissions),
            min_size=1,
            max_size=len(all_permissions),
            unique=True
        ))
        # Convert enum values to strings
        permissions = [p.value for p in permissions]
    
    api_key = draw(api_key_strategy())
    
    return ApiKey(
        id=uuid.uuid4(),
        user_id=user.id,
        user=user,
        key_hash=f"hashed_{api_key}",  # Simplified hash for testing
        key_prefix=api_key.split('_')[-1][:8] if '_' in api_key else api_key[:8],
        name=name or draw(api_key_name_strategy()),
        permissions=permissions,
        expires_at=expires_at or draw(st.datetimes(
            min_value=datetime.now() + timedelta(hours=1),
            max_value=datetime.now() + timedelta(days=365)
        )),
        is_active=is_active if is_active is not None else draw(st.booleans()),
        created_at=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )),
        updated_at=draw(st.one_of(st.none(), st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime.now()
        )))
    )


# --- Convenience Strategies ---

@composite
def user_with_wallet_strategy(draw, balance: Optional[int] = None):
    """Generate a User with an associated Wallet."""
    user = draw(user_strategy())
    wallet = draw(wallet_strategy(user=user, balance=balance))
    user.wallet = wallet
    return user


@composite
def positive_amount_strategy(draw):
    """Generate positive amounts for transactions."""
    return draw(st.integers(min_value=1, max_value=1000000))


@composite
def kobo_amount_strategy(draw):
    """Generate amounts in kobo (1-1000000 kobo = 0.01-10000 Naira)."""
    return draw(st.integers(min_value=1, max_value=1000000))


# --- Expiry Duration Strategies ---

@composite
def expiry_duration_strategy(draw):
    """Generate valid expiry duration strings."""
    return draw(st.sampled_from(["1H", "1D", "1M", "1Y"]))


# --- Permission Strategies ---

@composite
def permission_list_strategy(draw):
    """Generate lists of permissions."""
    all_permissions = [p.value for p in ApiKeyPermissions]
    return draw(st.lists(
        st.sampled_from(all_permissions),
        min_size=1,
        max_size=len(all_permissions),
        unique=True
    ))


# --- Authentication Helper Strategies ---

@composite
def jwt_token_strategy(draw, user_id: Optional[str] = None):
    """Generate JWT tokens for testing."""
    from app.auth_utils import create_access_token
    from datetime import timedelta
    
    if user_id is None:
        user_id = str(uuid.uuid4())
    
    expires_delta = draw(st.one_of(
        st.none(),
        st.timedeltas(min_value=timedelta(minutes=1), max_value=timedelta(hours=24))
    ))
    
    return create_access_token(data={"sub": user_id}, expires_delta=expires_delta)


@composite
def api_key_with_permissions_strategy(draw, permissions: Optional[list] = None):
    """Generate API key string with specific permissions."""
    import secrets
    from app.config import settings
    
    if permissions is None:
        permissions = draw(permission_list_strategy())
    
    random_part = secrets.token_urlsafe(32)
    plain_api_key = f"{settings.api_key_prefix}_{random_part}"
    
    return plain_api_key, permissions