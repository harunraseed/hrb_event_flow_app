# Production Setup & Migration Guide

## Problems
1. The production PostgreSQL database is missing `reset_token` and `reset_token_expires` columns in the `users` table
2. No superuser account exists in the production database

## Complete Setup Process

### Step 1: Set Environment Variables in Vercel
1. Go to your Vercel dashboard
2. Navigate to your project settings
3. Go to Environment Variables
4. Add these environment variables:
   
   **Migration Secret**:
   - **Name**: `MIGRATION_SECRET`
   - **Value**: Generate a secure random string (e.g., use a password generator)
   - **Environment**: Production
   
   **Setup Secret** (for initial user creation):
   - **Name**: `SETUP_SECRET`
   - **Value**: Generate another secure random string
   - **Environment**: Production

### Step 2: Deploy the Updated Code
1. Commit and push the current changes to your repository
2. Wait for Vercel to deploy the updated code

### Step 3: Check Application Status
1. First, check the setup status:
   ```
   https://your-app-domain.vercel.app/admin/setup/status
   ```
   This will show you what needs to be done.

### Step 4: Run Database Migration (if needed)
1. If reset columns are missing, run the migration:
   ```
   https://your-app-domain.vercel.app/admin/migrate/reset-tokens?secret=YOUR_MIGRATION_SECRET
   ```

### Step 5: Create Initial Superuser Account
1. Create your first superuser account:
   ```
   https://your-app-domain.vercel.app/admin/setup/initial-user?secret=YOUR_SETUP_SECRET&username=admin&email=your-email@gmail.com&password=your-secure-password
   ```
   
   Replace:
   - `YOUR_SETUP_SECRET` with the setup secret from Step 1
   - `admin` with your desired username
   - `your-email@gmail.com` with your email
   - `your-secure-password` with your secure password (min 6 chars)

2. You should see a success response:
   ```json
   {
     "status": "success",
     "message": "Superuser \"admin\" created successfully!",
     "username": "admin",
     "email": "your-email@gmail.com",
     "role": "superadmin",
     "user_id": 1
   }
   ```

### Step 6: Test Login
1. Go to your app's login page
2. Use the credentials you just created
3. You should now be able to log in successfully!

### Step 7: Security Cleanup
After successful setup:
1. **Remove both environment variables from Vercel**:
   - Remove `MIGRATION_SECRET`
   - Remove `SETUP_SECRET`
2. This prevents unauthorized access to setup endpoints

## Debug & Troubleshooting Endpoints

### Check Overall Status
```
https://your-app-domain.vercel.app/admin/setup/status
```
Shows database connection, tables, user count, and what setup steps are needed.

### Check Database Schema
```
https://your-app-domain.vercel.app/debug/db-schema
```
Shows the current database structure and all tables.

### Check Email Configuration
```
https://your-app-domain.vercel.app/debug/email-config
```
Shows email configuration (useful for other features).

## What Each Step Does

### Database Migration
- Adds `reset_token VARCHAR(100)` column to the `users` table
- Adds `reset_token_expires TIMESTAMP` column to the `users` table
- Enables password reset functionality

### Initial User Setup
- Creates the first superuser account in your production database
- Sets up admin access so you can log in
- Only works when no users exist (security feature)

## Alternative Manual Methods

### If Automated Migration Fails
Run these SQL commands directly in your PostgreSQL database:
```sql
ALTER TABLE users ADD COLUMN reset_token VARCHAR(100);
ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP;
```

### If User Creation Fails
Run this SQL command in your PostgreSQL database:
```sql
INSERT INTO users (username, email, password_hash, role, is_active, created_at) 
VALUES ('admin', 'your-email@gmail.com', 'HASHED_PASSWORD', 'superadmin', true, NOW());
```
(You'll need to hash the password first using bcrypt)

## Security Notes
- Setup endpoints only work with valid secret keys
- User creation only works when no users exist
- Remove environment variables after setup
- Always use strong passwords and secrets

## Future Deployments
- Database migration only needs to be run once
- User setup only needs to be done once
- Future deployments won't require these steps
- Keep your superuser credentials secure

## Troubleshooting Common Issues

### "Unauthorized setup attempt"
- Check that `SETUP_SECRET` is set correctly in Vercel
- Verify the secret in your URL matches exactly

### "Users already exist"
- This means setup was already completed
- Try logging in with existing credentials
- Or check with database admin

### "Database connection failed"
- Check your `DATABASE_URL` in Vercel settings
- Verify PostgreSQL database is accessible
- Check Supabase/database provider status

### Migration/Setup worked but login still fails
- Clear browser cache and cookies
- Check that the user account was actually created
- Verify password is correct (min 6 characters)