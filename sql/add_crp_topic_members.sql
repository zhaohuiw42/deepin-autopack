-- 为 global_config 表添加 CRP 主题默认成员字段
-- 创建 CRP 主题时自动把这些账号添加为主题成员（分号或逗号分隔的 LDAP 用户名）
ALTER TABLE global_config ADD COLUMN crp_topic_members TEXT COMMENT '创建CRP主题时自动添加的成员账号（分号或逗号分隔的LDAP用户名）';
