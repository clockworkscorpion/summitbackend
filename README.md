# summitbackend
Python backend for the Summit News app

SummIt News was designed as a "Tiktok" for news. This backend used derivatives of Stanford's Pointer Generator Network models (PGNs) to summarize relevant news articles every 20 minutes. The backend was built on a mixture of Google Cloud and AWS - hourly executions of the code were handled through AWS Lambda, and stored on DynamoDB (and S3 for cold backups), while cloud notifications and messaging were handled through Firebase Cloud Messaging. 

Many thanks to the folks at NewscatcherAPI who were very generous with sharing their learnings on Medium.

For more information about SummIt News, check out this link --> https://summitup.github.io/
