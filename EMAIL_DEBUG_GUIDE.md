# 📧 Email Debugging Guide for Vercel Deployment

## 🚨 Common Issues with Email on Vercel

### 1. **Missing Environment Variables**
Ensure these variables are set in your Vercel dashboard:

**Required Variables:**
```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=your_email@gmail.com
```

### 2. **Gmail App Password Setup**
If using Gmail, you MUST use an App Password, not your regular password:

1. Enable 2-Factor Authentication on your Google account
2. Go to Google Account Settings > Security > App passwords
3. Generate a new app password for "Mail"
4. Use this 16-character password as `MAIL_PASSWORD`

### 3. **Alternative Email Providers**
Consider switching to these more serverless-friendly options:

**SendGrid:**
```
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=your_sendgrid_api_key
```

**Mailgun:**
```
MAIL_SERVER=smtp.mailgun.org
MAIL_PORT=587
MAIL_USERNAME=your_mailgun_username
MAIL_PASSWORD=your_mailgun_password
```

## 🔧 Testing Steps

### Step 1: Check Environment Variables
Visit: `https://your-vercel-app.vercel.app/debug/email`

This will show you:
- All email configuration values
- Whether environment variables are loaded
- SMTP connection test results

### Step 2: Send Test Email
Visit: `https://your-vercel-app.vercel.app/debug/send_test_email`

This will:
- Send a simple test email to your configured email
- Return detailed error messages if it fails

### Step 3: Test with Real Data
Visit: `https://your-vercel-app.vercel.app/test_single_email/<participant_id>`

Replace `<participant_id>` with an actual participant ID to test the full email flow.

## 🐛 Common Error Messages

### "Authentication failed"
- Check if you're using App Password (for Gmail)
- Verify MAIL_USERNAME and MAIL_PASSWORD are correct

### "Connection timeout"
- Vercel may be blocking SMTP connections
- Try a different email service like SendGrid

### "Missing email configuration"
- Environment variables not set in Vercel
- Go to Vercel Dashboard > Project > Settings > Environment Variables

### "Mail server not responding"
- SMTP server may be blocked by Vercel
- Use email service APIs instead of SMTP

## 🚀 Recommended Solution: SendGrid

1. **Sign up for SendGrid** (free tier: 100 emails/day)
2. **Get API Key** from SendGrid dashboard
3. **Update Vercel environment variables:**
   ```
   MAIL_SERVER=smtp.sendgrid.net
   MAIL_PORT=587
   MAIL_USERNAME=apikey
   MAIL_PASSWORD=SG.your_actual_api_key_here
   ```
4. **Verify sender email** in SendGrid dashboard

## 📝 Environment Variables Checklist

- [ ] MAIL_SERVER is set
- [ ] MAIL_PORT is set (587 for TLS)
- [ ] MAIL_USERNAME is set
- [ ] MAIL_PASSWORD is set (App Password for Gmail)
- [ ] MAIL_DEFAULT_SENDER is set
- [ ] All variables are correctly saved in Vercel
- [ ] Redeployed after setting variables

## 🔍 Debug URLs

Add these to your deployed app URL:

1. **Config Check:** `/debug/email`
2. **Simple Test:** `/debug/send_test_email`
3. **Participant Test:** `/test_single_email/<participant_id>`

## 💡 Pro Tips

1. **Always use HTTPS** in production
2. **Test with a small participant list** first
3. **Monitor Vercel function logs** for detailed errors
4. **Set up email webhooks** for delivery tracking
5. **Consider email queues** for large batches

## 🆘 If Nothing Works

1. **Check Vercel Function Logs:**
   - Go to Vercel Dashboard > Functions tab
   - Check recent invocations for error messages

2. **Try Alternative Email Services:**
   - SendGrid (recommended for serverless)
   - Mailgun
   - AWS SES
   - Resend

3. **Contact Support:**
   - Vercel support for connection issues
   - Email provider support for authentication

## 📊 Next Steps After Fixing

1. Test with 1-2 participants first
2. Monitor email delivery rates
3. Set up bounce handling
4. Add email analytics/tracking
5. Consider rate limiting for large events