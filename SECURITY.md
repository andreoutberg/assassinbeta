# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Currently supported versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of Andre Assassin seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please do NOT:
- Open a public GitHub issue
- Post about it on social media
- Exploit the vulnerability

### Please DO:
- Email us at: **security@andreassassin.com**
- Include detailed steps to reproduce the issue
- Include the version of Andre Assassin you're using
- Include any relevant logs or screenshots

### What to expect:
1. **Acknowledgment**: We'll acknowledge receipt within 24 hours
2. **Assessment**: We'll assess the vulnerability within 48 hours
3. **Fix Timeline**: We'll provide an estimated timeline for the fix
4. **Updates**: We'll keep you informed about our progress
5. **Credit**: We'll credit you in our release notes (unless you prefer to remain anonymous)

## Security Best Practices for Users

### API Keys
- **NEVER** commit API keys to version control
- Store API keys in `.env` files (never commit `.env`)
- Use read-only API keys where possible
- Rotate API keys regularly
- Use IP whitelisting on exchange APIs

### Deployment Security
1. **Use HTTPS**: Always use SSL/TLS in production
2. **Firewall**: Configure firewall rules to restrict access
3. **Updates**: Keep all dependencies up to date
4. **Monitoring**: Set up alerts for suspicious activity
5. **Backups**: Regular encrypted backups of your database

### Authentication & Access
- Use strong, unique passwords (minimum 16 characters)
- Enable 2FA on all exchange accounts
- Limit API permissions to minimum required
- Regularly audit access logs
- Use separate accounts for testing and production

### Network Security
- Whitelist IP addresses for webhook access
- Use VPN for remote access
- Configure rate limiting
- Enable DDoS protection
- Monitor for unusual traffic patterns

### Docker Security
```bash
# Run containers as non-root user
docker run --user 1000:1000 andre-assassin

# Use read-only file systems where possible
docker run --read-only andre-assassin

# Limit resources
docker run --memory="1g" --cpus="2" andre-assassin
```

### Database Security
- Use strong passwords for database accounts
- Encrypt sensitive data at rest
- Use SSL for database connections
- Regular security audits
- Implement query timeouts

## Security Checklist

Before deploying to production:

- [ ] All API keys are in environment variables
- [ ] `.env` file is in `.gitignore`
- [ ] HTTPS/SSL is configured
- [ ] Firewall rules are configured
- [ ] Rate limiting is enabled
- [ ] Webhook authentication is enabled
- [ ] Database uses strong passwords
- [ ] Docker images are from trusted sources
- [ ] Monitoring and alerting is configured
- [ ] Backup strategy is in place
- [ ] Incident response plan exists
- [ ] Dependencies are up to date
- [ ] Security headers are configured (CORS, CSP, etc.)
- [ ] Input validation is implemented
- [ ] Error messages don't leak sensitive info

## Known Security Considerations

### Third-party Dependencies
We regularly audit our dependencies for known vulnerabilities using:
- GitHub Dependabot
- Snyk vulnerability scanning
- Manual security reviews

### Data Privacy
- We don't collect personal data
- Trading data is stored locally
- No telemetry or analytics
- All data stays on your infrastructure

## Vulnerability Disclosure Policy

When we receive a security bug report, we will:

1. Confirm the problem and determine affected versions
2. Audit code to find similar problems
3. Prepare fixes for all supported versions
4. Release new security fix versions
5. Prominently announce the fix in release notes

## Security Updates

Security updates will be released as:
- **PATCH** version for minor security fixes
- **MINOR** version for significant security improvements
- **MAJOR** version only if breaking changes are required

Subscribe to security announcements:
- Watch this repository on GitHub
- Enable security alerts in your GitHub settings
- Follow our security advisory page

## Compliance

Andre Assassin is designed with security best practices but does not claim compliance with specific standards. Users are responsible for ensuring their deployment meets their regulatory requirements.

## Contact

For security concerns, contact: **security@andreassassin.com**

For general support: **support@andreassassin.com**

---

*Last Updated: November 10, 2025*