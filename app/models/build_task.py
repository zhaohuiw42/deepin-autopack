"""打包任务模型"""
from datetime import datetime
from app import db


def _utc_iso(dt):
    """将 naive UTC 时间序列化为带 `Z` 后缀的 ISO-8601 字符串。

    项目所有时间戳都以 naive UTC（``datetime.utcnow``）存储。直接用
    ``.isoformat()`` 得到的字符串没有时区标记，浏览器 ``new Date(isoStr)``
    会按本地时区解析，导致显示时间整体偏移本地 UTC 偏移量（如东八区偏 8
    小时）。补上 ``Z`` 后值为明确的 UTC，前端即可正确显示本地时间。
    """
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


class BuildTask(db.Model):
    """打包任务模型"""
    __tablename__ = 'build_tasks'
    
    # 基础信息
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    project_name = db.Column(db.String(255), nullable=False)  # 冗余字段，方便查询
    
    # 打包配置
    package_mode = db.Column(db.String(20), nullable=False)  # 'normal', 'changelog_only', 'crp_only', 'github_action'
    version = db.Column(db.String(50), nullable=False)  # 版本号
    architectures = db.Column(db.JSON)  # 架构列表 ['amd64', 'arm64', 'loongarch64', 'riscv64']
    crp_topic_id = db.Column(db.String(50))  # CRP主题ID（可选）
    crp_topic_name = db.Column(db.String(255))  # CRP主题名称（可选）
    crp_branch_id = db.Column(db.Integer)  # CRP分支ID（可选，为空时使用全局配置）
    start_commit_hash = db.Column(db.String(40), nullable=False)  # 起始commit
    
    # GitHub Action 相关（package_mode='github_action' 时使用）
    github_action_name = db.Column(db.String(200))  # GitHub Action workflow 名称
    github_action_inputs = db.Column(db.Text)  # GitHub Action 输入参数（JSON格式）
    github_action_run_id = db.Column(db.String(50))  # GitHub Action Run ID
    github_action_run_url = db.Column(db.String(500))  # GitHub Action Run URL
    
    # 任务状态
    status = db.Column(db.String(20), default='pending')  
    # pending/running/paused/success/failed/cancelled
    current_step = db.Column(db.Integer, default=0)  # 当前执行到第几步（从0开始）
    error_message = db.Column(db.Text)  # 错误信息
    
    # GitHub相关
    github_branch = db.Column(db.String(100))  # 创建的打包分支名
    github_pr_number = db.Column(db.Integer)  # PR编号
    github_pr_url = db.Column(db.String(500))  # PR链接
    github_pr_status = db.Column(db.String(20))  # open/merged/closed
    
    # Gerrit同步状态（仅GitHub项目）
    gerrit_synced = db.Column(db.Boolean, default=False)  # 是否已同步到Gerrit
    gerrit_commit_hash = db.Column(db.String(40))  # Gerrit上的commit hash
    
    # CRP打包状态
    crp_build_id = db.Column(db.String(100))  # CRP打包任务ID
    crp_build_status = db.Column(db.String(20))  # pending/building/success/failed
    crp_build_url = db.Column(db.String(500))  # CRP打包任务链接
    crp_commit_hash = db.Column(db.String(40))  # CRP打包使用的commit hash（包hash）
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = db.Column(db.DateTime)  # 任务开始时间
    completed_at = db.Column(db.DateTime)  # 任务完成时间
    
    # 关联关系
    steps = db.relationship('BuildTaskStep', backref='task', cascade='all, delete-orphan', 
                           order_by='BuildTaskStep.step_order')
    project = db.relationship('Project', backref='build_tasks')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'package_mode': self.package_mode,
            'version': self.version,
            'architectures': self.architectures or [],
            'crp_topic_id': self.crp_topic_id,
            'github_action_name': self.github_action_name,
            'github_action_inputs': self.github_action_inputs,
            'github_action_run_id': self.github_action_run_id,
            'github_action_run_url': self.github_action_run_url,
            'status': self.status,
            'current_step': self.current_step,
            'error_message': self.error_message,
            'github_branch': self.github_branch,
            'github_pr_number': self.github_pr_number,
            'github_pr_url': self.github_pr_url,
            'github_pr_status': self.github_pr_status,
            'gerrit_synced': self.gerrit_synced,
            'crp_build_id': self.crp_build_id,
            'crp_build_status': self.crp_build_status,
            'crp_build_url': self.crp_build_url,
            'crp_topic_name': self.crp_topic_name,
            'crp_branch_id': self.crp_branch_id,
            'crp_commit_hash': self.crp_commit_hash,
            'created_at': _utc_iso(self.created_at),
            'updated_at': _utc_iso(self.updated_at),
            'started_at': _utc_iso(self.started_at),
            'completed_at': _utc_iso(self.completed_at),
            'steps': [step.to_dict() for step in self.steps]
        }


class BuildTaskStep(db.Model):
    """打包任务步骤模型"""
    __tablename__ = 'build_task_steps'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('build_tasks.id'), nullable=False)
    step_order = db.Column(db.Integer, nullable=False)  # 步骤顺序（从0开始）
    step_name = db.Column(db.String(100), nullable=False)  # 步骤名称
    step_description = db.Column(db.String(255))  # 步骤描述
    status = db.Column(db.String(20), default='pending')  # pending/running/completed/failed/skipped
    log_message = db.Column(db.Text)  # 日志信息
    error_message = db.Column(db.Text)  # 错误信息
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, default=0)  # 重试次数
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'step_order': self.step_order,
            'step_name': self.step_name,
            'step_description': self.step_description,
            'status': self.status,
            'log_message': self.log_message,
            'error_message': self.error_message,
            'started_at': _utc_iso(self.started_at),
            'completed_at': _utc_iso(self.completed_at),
            'retry_count': self.retry_count
        }
