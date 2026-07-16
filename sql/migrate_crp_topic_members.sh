#!/bin/bash
# CRP 主题默认成员字段迁移脚本
# 用法: bash sql/migrate_crp_topic_members.sh
# 可通过环境变量覆盖: DB_NAME / DB_USER / DB_PASSWORD

DB_NAME="${DB_NAME:-deepin_autopack}"
DB_USER="${DB_USER:-root}"

echo "=== CRP 主题默认成员字段迁移 ==="
echo "数据库: ${DB_NAME}"
echo "用户: ${DB_USER}"
echo ""

if [ -n "${DB_PASSWORD}" ]; then
    MYSQL_PWD="${DB_PASSWORD}" mysql -u "${DB_USER}" "${DB_NAME}" <<SQL
ALTER TABLE global_config ADD COLUMN IF NOT EXISTS crp_topic_members TEXT COMMENT '创建CRP主题时自动添加的成员账号（分号或逗号分隔的LDAP用户名）';
SQL
else
    mysql -u "${DB_USER}" "${DB_NAME}" <<SQL
ALTER TABLE global_config ADD COLUMN IF NOT EXISTS crp_topic_members TEXT COMMENT '创建CRP主题时自动添加的成员账号（分号或逗号分隔的LDAP用户名）';
SQL
fi

if [ $? -eq 0 ]; then
    echo "迁移完成"
else
    echo "迁移失败，请检查数据库连接"
    exit 1
fi
