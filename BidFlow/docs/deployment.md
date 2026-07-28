# BidFlow 云服务器部署

本文档适用于 Ubuntu 22.04/24.04，MySQL 和 Milvus 已部署在同一台服务器。

## 1. 安装运行环境

```bash
apt update
apt install -y git curl ca-certificates build-essential pkg-config libmariadb-dev python3 python3-venv python3-pip nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

## 2. 获取代码与安装依赖

将仓库放在 `/opt/bidflow`。不要把 Nginx 站点部署在 `/root` 下，因为 `www-data` 无法读取该目录。

```bash
git clone -b bugfix/startup-bootstrap https://github.com/YJR-1996/BidFlow.git /opt/bidflow-repo
cp -a /opt/bidflow-repo/BidFlow/. /opt/bidflow/
cd /opt/bidflow/backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cd /opt/bidflow/frontend
npm install
npm run build
```

## 3. 配置环境变量

```bash
cd /opt/bidflow/backend
cp ../.env.example .env
chmod 600 .env
nano .env
```

必须填写：`MYSQL_HOST`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`、`SECRET_KEY`、`MILVUS_HOST`、`DASHSCOPE_API_KEY`。

MySQL 和 Milvus 同机时，`MYSQL_HOST` 与 `MILVUS_HOST` 填 `127.0.0.1`。

## 4. 启动后端

```bash
cp /opt/bidflow/deploy/bidflow.service /etc/systemd/system/bidflow.service
chown -R www-data:www-data /opt/bidflow
systemctl daemon-reload
systemctl enable --now bidflow
systemctl status bidflow --no-pager
curl http://127.0.0.1:8001/api/health
```

## 5. 配置 Nginx

```bash
cp /opt/bidflow/deploy/nginx-bidflow.conf /etc/nginx/sites-available/bidflow
ln -sf /etc/nginx/sites-available/bidflow /etc/nginx/sites-enabled/bidflow
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

浏览器访问 `http://服务器公网IP/`；接口文档为 `http://服务器公网IP/docs`。

## 更新流程

```bash
cd /opt/bidflow-repo
git fetch origin
git checkout bugfix/startup-bootstrap
git pull --ff-only origin bugfix/startup-bootstrap
cp -a /opt/bidflow-repo/BidFlow/. /opt/bidflow/
cd /opt/bidflow/backend && .venv/bin/pip install -r requirements.txt
cd /opt/bidflow/frontend && npm install && npm run build
systemctl restart bidflow
systemctl reload nginx
```
