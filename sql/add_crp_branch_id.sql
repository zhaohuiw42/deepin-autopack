-- 打包任务表添加 CRP 分支 ID 字段
ALTER TABLE build_tasks ADD COLUMN crp_branch_id INT NULL COMMENT 'CRP分支ID（可选，为空时使用全局配置）';
