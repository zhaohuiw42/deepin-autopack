-- 打包任务表添加 CRP 打包使用的 commit hash 字段（包hash）
ALTER TABLE build_tasks ADD COLUMN crp_commit_hash VARCHAR(40) NULL COMMENT 'CRP打包使用的commit hash（包hash）' AFTER crp_build_url;
