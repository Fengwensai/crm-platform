-- 客户/员工管理平台 - 本地开发数据库初始化
-- 用法（在 backend 目录下执行，需输入 postgres 超级用户密码）：
--   "/d/PostgreSQL/15/bin/psql.exe" -U postgres -h localhost -f scripts/create_db.sql
--
-- 应用用户密码与 backend/.env 中 DATABASE_URL 保持一致（仅本地开发用；
-- 生产环境密码由服务器上随机生成，不在此文件、也不入库）。

CREATE USER crm WITH PASSWORD 'Crm_2026_P';
CREATE DATABASE crm_admin OWNER crm ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE crm_admin TO crm;
