database seeding: 
    python scripts/seed.py --quick
    quick, smart-rotate, full

# Increase batch size
python scripts/match_existing_products.py --limit 200 --no-ai
#daily job 
python jobs/daily_scrape.py --force-all

---------------------all platform
testing :
    python scripts/test_scrapers.py --platform all --query "smartphone" --standalone

---------------------individual

Amazon (Captcha & Stealth Check):
    python scripts/test_scrapers.py --platform amazon --query "iphone 15" --standalone

Flipkart (JS Extraction Check):
    python scripts/test_scrapers.py --platform flipkart --query "gaming laptop" --standalone

Nykaa (JSON-LD Check):
    python scripts/test_scrapers.py --platform nykaa --query "lipstick" --standalone

Meesho (Akamai Bypass Check):
    python scripts/test_scrapers.py --platform meesho --query "saree" --standalone





curl -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@gmail.com",
    "password": "123456",
    "returnSecureToken": true
  }'
<<<<<<< HEAD
=======

eyJhbGciOiJSUzI1NiIsImtpZCI6ImEyZGZiOGEzOGI1MmQ5ZjA5ZWRjYWE1MDcwYTBlOGYwYTllMDk4YmEiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vZGVhbGh1bnQtOTM5NDgiLCJhdWQiOiJkZWFsaHVudC05Mzk0OCIsImF1dGhfdGltZSI6MTc3Mzc2Mzg4OSwidXNlcl9pZCI6InJQb2UwSmZUMVlTNFhNWHBSUEthZDJ5bUdpdDEiLCJzdWIiOiJyUG9lMEpmVDFZUzRYTVhwUlBLYWQyeW1HaXQxIiwiaWF0IjoxNzczNzYzODg5LCJleHAiOjE3NzM3Njc0ODksImVtYWlsIjoidGVzdHVzZXJAZ21haWwuY29tIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJmaXJlYmFzZSI6eyJpZGVudGl0aWVzIjp7ImVtYWlsIjpbInRlc3R1c2VyQGdtYWlsLmNvbSJdfSwic2lnbl9pbl9wcm92aWRlciI6InBhc3N3b3JkIn19.An7b-eShg4_UbCRYSK5tAxy-8Mn5iAXGm6K0Up_SZQYM9qepj1PgB5Qxp1xUcvV092aZo1Y6b8ns5KVJA-vDVngU4FeF101bj6f_1LIg7S9VAv_238Ay6UohJNhOTW6tJevGEMByOIinRoQMKWLA7welfaQExAI32OTKVCCkvc2Qst30fGb9bvYINcRhS7QW9ATNgdy4OSU-1KdVmFOVjbP_o-dkM526RrKaKw4deoodINHWkbIMEIPwhHZ_JDAO7-VtpSxt1gZNDbgB2FsuXzwy3-un03ZcvP2IkOX6r_t_4So1HsrVGdrsoQH_xHd8vVwyJsjAe4D3VD-wMk9vjg
>>>>>>> eebb940 (Testing limits, varients, status Upgrade)
