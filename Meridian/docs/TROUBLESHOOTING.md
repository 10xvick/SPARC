# JIRA API Connection Issues - Troubleshooting Guide

## SSL/Connection Errors

If you encounter SSL errors like:
```
SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1010)'))
```

### What Was Fixed

The fetch script now includes **robust error handling** and **automatic retry logic**:

✅ **Automatic Retries**: Up to 3 attempts per request with exponential backoff
✅ **Smart Delays**: 5, 10, 15 seconds between retry attempts
✅ **SSL Error Handling**: Specific handling for SSL/TLS errors with longer backoff (10, 20, 30 seconds)
✅ **Rate Limit Detection**: Automatically detects HTTP 429 and respects `Retry-After` header
✅ **Timeout Handling**: Increased timeout from 30 to 60 seconds
✅ **Connection Pooling**: Uses requests session with HTTPAdapter for better connection management
✅ **Request Throttling**: 2-second delay between successful requests to prevent rate limiting

### Retry Strategy

The script will automatically:

1. **Attempt 1**: Try the request
2. **If fails**: Wait and retry (with increasing delays)
3. **Attempt 2**: Second try with 5-second delay
4. **Attempt 3**: Final try with 10-second delay

For **SSL errors specifically**:
- **Attempt 1**: Initial try
- **If fails**: Wait 10 seconds
- **Attempt 2**: Second try
- **If fails**: Wait 20 seconds
- **Attempt 3**: Final try
- **If fails**: Wait 30 seconds, then skip project

### Error Messages You'll See

The improved error handling provides clearer messages:

```
✅ Success:
   ✓ Fetched 50 issues from project AS
   
⏳ Retrying:
   ⏳ Waiting 5 seconds before retry 2/3...
   🔄 Retrying with backoff... (attempt 2/3)
   
❌ Rate Limited:
   ⚠️  Rate limited. Waiting 60 seconds...
   
❌ SSL Error:
   ❌ SSL Error: [SSL: UNEXPECTED_EOF_WHILE_READING]...
   🔄 Retrying with backoff... (attempt 2/3)
   
❌ Final Failure:
   ⚠️  Skipping project FH after 3 SSL failures
```

### Manual Solutions

If errors persist after automatic retries:

#### 1. Check Network Connection
```bash
# Test connectivity to JIRA
curl -I https://hclsw-jiracentral-eng.atlassian.net

# Check DNS resolution
nslookup hclsw-jiracentral-eng.atlassian.net
```

#### 2. Run with Longer Delays
Edit `jira_config.json` and reduce `maxResults`:
```json
{
  "default": {
    "maxResults": 25  // Reduce from 50 to 25
  }
}
```

This fetches fewer items per request, reducing connection time.

#### 3. Run Projects Individually
If a specific project keeps failing, you can temporarily remove it from the config:

```json
{
  "projects": {
    "AS": {},
    "HR": {},
    // "FH": {},  // Comment out problematic project
    "PCS": {}
  }
}
```

Then run the fetch and add it back later.

#### 4. Check JIRA API Status
Visit: https://status.atlassian.com/
Check if JIRA Cloud is experiencing issues.

#### 5. Verify API Token
Ensure your API token is still valid:
```bash
curl -u "your.email@example.com:YOUR_API_TOKEN" \
  https://hclsw-jiracentral-eng.atlassian.net/rest/api/3/myself
```

If you get a 401 error, regenerate your API token.

#### 6. Use VPN/Different Network
Sometimes corporate networks or firewalls can interfere:
- Try from a different network
- Use a VPN
- Check with IT about SSL inspection/firewalls

### Rate Limiting

JIRA Cloud has rate limits:
- **Standard**: ~100 requests per minute
- **Premium**: ~1000 requests per minute

The script now:
- Adds 2-second delays between requests (max 30 requests/minute)
- Automatically backs off when rate limited
- Respects `Retry-After` headers

### Best Practices

1. **Run during off-peak hours**: Less network congestion
2. **Use incremental updates**: After initial fetch, subsequent runs are faster
3. **Monitor output**: Watch for patterns in which projects fail
4. **Use checkpoint system**: Script saves progress, so you can resume

### Advanced: Disable SSL Verification (NOT RECOMMENDED)

⚠️ **Only use this for debugging, never in production:**

Add to the fetch method:
```python
response = session.post(url, headers=headers, json=payload, timeout=60, verify=False)
```

And suppress warnings:
```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

This bypasses SSL certificate verification. Only use temporarily to diagnose issues.

### Getting Help

If issues persist:

1. **Check logs**: Look for patterns in error messages
2. **Test API directly**: Use curl or Postman to test JIRA API
3. **Contact JIRA support**: If the issue is server-side
4. **Check quotas**: Ensure your JIRA plan has sufficient API quota

### Summary of Improvements

The enhanced script provides:

| Feature | Before | After |
|---------|--------|-------|
| Retry Logic | ❌ None | ✅ 3 attempts with backoff |
| SSL Error Handling | ❌ Immediate fail | ✅ Smart retry with delays |
| Rate Limit Detection | ❌ None | ✅ Auto-detect and wait |
| Timeout | 30 seconds | 60 seconds |
| Connection Pooling | ❌ New connection each time | ✅ Session with adapter |
| Request Throttling | ❌ None | ✅ 2-second delay between requests |
| Error Messages | Generic | Specific and actionable |

The script will now handle temporary network issues automatically and provide clear feedback when manual intervention is needed.
