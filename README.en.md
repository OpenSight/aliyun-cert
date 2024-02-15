### Purpose
Request and renew free certificates from let's encrypt for Aliyun CDN domains.

### Prepare
Install `certbot` with aliyun DNS plugin and `aliyun-cert`
``` shell
python3 -m venv aliyun-cert
aliyun-cert/bin/pip install .
ln -s aliyun-cert/bin/certbot /usr/bin/certbot
ln -s aliyun-cert/bin/aliyun-cert /usr/bin/aliyun-cert
```

Create config file `~/.secrets/aliyun.ini` for aliyun access key
``` ini
dns_aliyun_key_id = xxx
dns_aliyun_key_secret = yyy
```

### Request Certificates from let's encrypt
``` shell
# request new cert
certbot certonly \
  --authenticator dns-aliyun \
  --dns-aliyun-propagation-seconds 30 \
  --dns-aliyun-credentials ~/.secrets/aliyun.ini \
  -d example.com -d *.example.com
```

### Deploy certificate for aliyun CDN domains
``` shell
# upload certificate
aliyun-cert upload-cert --domain example.com /etc/letsencrypt/live/example.com/fullchain.pem /etc/letsencrypt/live/example.com/privkey.pem

# deploy certificates with certificates id returned from last command
aliyun-cert set-cert --cert-id 123456 --domain cdn.example.com --service cdn

# check all SSL-enabled CDN domains and their certificates
aliyun-cert list-domains --cdn
```

### Renew Certificates
Create crontab file `/etc/cron.d/certbot`
``` crontab
0 0,12 * * * root sleep 1471 && certbot renew -q
```

Create deploy hook to update aliyun CDN's certification in `/etc/letsencrypt/renewal-hooks/deploy/09-deploy-aliyun.sh`
``` shell
#!/bin/bash

aliyun-cert certbot-deploy-hook --cdn --delete-old-cert
```

