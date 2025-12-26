# Password Checking Analysis

## Summary
Password checking happens in multiple places in the application:

---

## 1. **Password Hash Generation & Checking** (`index.py` lines 947-957)
```python
def set_password(self, password):
    """Hash and set password"""
    self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(self, password):
    """Check if provided password matches hash"""
    return bcrypt.check_password_hash(self.password_hash, password)

# Add methods to User class
User.set_password = set_password
User.check_password = check_password
```

**Location:** `index.py` lines 947-957
**Method:** Uses Flask-Bcrypt for hashing and verification
**Key Point:** Password hash is stored in `password_hash` column

---

## 2. **Login Route** (`index.py` lines 1440-1485)
The login route has TWO password check paths:

### Path A: Manual Validation (lines 1448-1463)
```python
if request.method == 'POST' and not form.validate_on_submit():
    # Try manual validation
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    
    if username and password:
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active:
            # Login user...
```

### Path B: Form Validation (lines 1467-1485)
```python
if form.validate_on_submit():
    username = form.username.data.strip()
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(form.password.data) and user.is_active:
        # Login user...
```

**Location:** `index.py` lines 1440-1485
**Key Point:** Password checked using `user.check_password()` method
**Requirements:** User must be:
1. Found in database (username match)
2. Password must match hash
3. User must be active (`is_active=True`)

---

## 3. **Password Reset** (`index.py` line 1693)
```python
if current_user.check_password(form.current_password.data):
    # Allow password change...
```

**Location:** `index.py` line 1693
**Purpose:** Verify current password before allowing new password

---

## 4. **Debug Script** (`debug_admin_user.py`)
Script to verify admin password in database:

```python
# Find admin user
admin = User.query.filter_by(username='admin').first()

# Test password
test_password = "Admin@123"
is_valid = bcrypt.check_password_hash(admin.password_hash, test_password)
```

**Location:** `debug_admin_user.py` lines 28-50
**Purpose:** Check if password matches hash in database
**Default Password:** `Admin@123`

---

## 5. **Password Reset Helper** (`reset_admin_password.py`)
Script to generate bcrypt hash for manual password reset:

```python
NEW_PASSWORD = "Admin@123"
password_hash = bcrypt.generate_password_hash(NEW_PASSWORD).decode('utf-8')
```

**Location:** `reset_admin_password.py`
**Purpose:** Generate hash to manually update in database

---

## Common Password Check Issues

1. **User not found** - Check if username exists in `users` table
2. **Password hash mismatch** - Password must be hashed with Bcrypt
3. **User not active** - Check `is_active` field is `True`
4. **Wrong password** - Verify using `debug_admin_user.py`
5. **Database connection** - Ensure DATABASE_URL is set correctly

---

## How to Debug

### Step 1: Run the debug script
```bash
python debug_admin_user.py
```

This will:
- Find the admin user
- Test if password matches hash
- Show password validity
- Auto-update if needed

### Step 2: Check user in database
- Username: `admin`
- Password default: `Admin@123`
- Role: `superadmin`
- Active: `True`

### Step 3: Reset password if needed
1. Run `reset_admin_password.py` to get hash
2. Update password_hash in Supabase
3. Test login again
