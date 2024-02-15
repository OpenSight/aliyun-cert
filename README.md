### 功能

通过本脚本可以为阿里云的 `CDN` 以及 `直播服务` 域名申请配置以及自动续期免费的 let's encrypt 证书。 [DOC EN](https://github.com/OpenSight/aliyun-cert/blob/main/README.en.md)

### 安装和配置

本脚本仅支持 Python 3
``` shell
pip install aliyun-cert
```

需要配置阿里云 ram 账号的 access key，并至少赋予用户如下权限：
- AliyunDNSFullAccess
- AliyunCDNFullAccess
- AliyunYundunCertFullAccess

如需同时配置直播 CDN 的证书，还需赋予如下权限：
- AliyunLiveFullAccess

access key 记录在一个文件中，比如 `~/.serects/aliyun.ini`，格式如下 
``` ini
dns_aliyun_key_id = xxx
dns_aliyun_key_secret = yyy
```

### 申请并配置证书

证书支持多域名，以及通配符域名，根据自己情况替换下面的 `example.com` 以及 `*.example.com`

``` shell
certbot certonly \
  --authenticator dns-aliyun \
  --dns-aliyun-propagation-seconds 30 \
  --dns-aliyun-credentials ~/.secrets/aliyun.ini \
  -d example.com -d *.example.com
```

为阿里云配置证书

``` shell
# 上传证书到阿里云 cas 服务
aliyun-cert upload-cert --domain example.com /etc/letsencrypt/live/example.com/fullchain.pem /etc/letsencrypt/live/example.com/privkey.pem

# 为 CDN 域名配置证书，cert-id 为上一步返回的 id
aliyun-cert set-cert --cert-id 123456 --domain cdn.example.com --service cdn
```

查看证书情况

``` shell
# 显示阿里云证书服务上所有上传上去的证书
aliyun-cert list-certs

# 显示所有开通了 HTTPS 的 CDN 域名及其证书情况
aliyun-cert lish-domains --cdn
```

### 证书续期

创建 crontab 文件 `/etc/cron.d/certbot`
``` crontab
0 0,12 * * * root sleep 1471 && certbot renew -q
```

创建 certbot 的 deploy hook 脚本，每次 certbot 成功续期续期证书后都会自动调用改脚本上传证书并配置阿里云的服务 `/etc/letsencrypt/renewal-hooks/deploy/09-deploy-aliyun.sh`
``` shell
#!/bin/bash

aliyun-cert certbot-deploy-hook --cdn --delete-old-cert
```
