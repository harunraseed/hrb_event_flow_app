# Database Migration Fix for Production Deployment

## Problem
The production PostgreSQL database is missing `reset_token` and `reset_token_expires` columns in the `users` table, causing 500 errors when users try to log in.

## Solution

### Step 1: Set Migration Secret in Vercel
1. Go to your Vercel dashboard
2. Navigate to your project settings
3. Go to Environment Variables
4. Add a new environment variable:
   - **Name**: `MIGRATION_SECRET`
   - **Value**: Generate a secure random string (e.g., use a password generator)
   - **Environment**: Production

### Step 2: Deploy the Updated Code
1. Commit and push the current changes to your repository
2. Wait for Vercel to deploy the updated code

### Step 3: Run the Migration
1. Once deployed, visit your production app migration endpoint:
   ```
   https://your-app-domain.vercel.app/admin/migrate/reset-tokens?secret=YOUR_MIGRATION_SECRET
   ```
   Replace:
   - `your-app-domain.vercel.app` with your actual Vercel domain
   - `YOUR_MIGRATION_SECRET` with the secret you set in Step 1

2. You should see a JSON response like:
   ```json
   {
     "status": "success",
     "message": "Password reset token migration completed successfully!",
     "results": ["Added reset_token column", "Added reset_token_expires column"],
     "columns_added": 2
   }
   ```

### Step 4: Verify the Fix
1. Try logging into your application
2. The 500 error should be resolved

### Step 5: Security Cleanup (Optional but Recommended)
After running the migration successfully:
1. Remove the `MIGRATION_SECRET` environment variable from Vercel
2. The migration endpoint will become inaccessible

## Debug Endpoints
If you need to troubleshoot:

### Check Database Schema
```
https://your-app-domain.vercel.app/debug/db-schema
```
This will show you the current database structure.

### Check Application Configuration
```
https://your-app-domain.vercel.app/debug/email-config
```
This shows email configuration (useful for other features).

## What This Migration Does
- Adds `reset_token VARCHAR(100)` column to the `users` table
- Adds `reset_token_expires TIMESTAMP` column to the `users` table
- Enables password reset functionality
- Makes the User model compatible with the current codebase

## Alternative Manual Method (If Automated Migration Fails)
If the automated migration doesn't work, you can manually run these SQL commands in your PostgreSQL database:

```sql
ALTER TABLE users ADD COLUMN reset_token VARCHAR(100);
ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP;
```

## Future Deployments
This migration only needs to be run once. Future deployments won't require this step.