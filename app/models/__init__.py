from app import db
from app.models.build_task import BuildTask, BuildTaskStep

class Project(db.Model):
    """项目配置模型"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, comment='项目名')
    gerrit_url = db.Column(db.String(500), comment='Gerrit地址')
    gerrit_branch = db.Column(db.String(100), comment='Gerrit分支')
    gerrit_repo_url = db.Column(db.String(200), comment='Gerrit仓库地址（用于克隆）')
    github_url = db.Column(db.String(500), comment='GitHub地址')
    github_branch = db.Column(db.String(100), comment='GitHub分支')
    last_commit_hash = db.Column(db.String(40), comment='上一次打包的commit hash')
    local_repo_path = db.Column(db.String(500), comment='本地仓库路径')
    repo_status = db.Column(db.String(20), default='pending', comment='仓库状态: pending/cloning/ready/error')
    repo_error = db.Column(db.Text, comment='错误信息')
    crp_project_name = db.Column(db.String(100), comment='CRP项目名称（默认为name-v25）')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'gerrit_url': self.gerrit_url,
            'gerrit_branch': self.gerrit_branch,
            'gerrit_repo_url': self.gerrit_repo_url,
            'github_url': self.github_url,
            'github_branch': self.github_branch,
            'last_commit_hash': self.last_commit_hash,
            'local_repo_path': self.local_repo_path,
            'repo_status': self.repo_status,
            'repo_error': self.repo_error,
            'crp_project_name': self.crp_project_name or f"{self.name}-v25"
        }
    
    def __repr__(self):
        return f'<Project {self.name}>'


class GlobalConfig(db.Model):
    """全局配置模型（单例模式）"""
    __tablename__ = 'global_config'
    
    id = db.Column(db.Integer, primary_key=True, default=1)
    ldap_username = db.Column(db.String(100), comment='LDAP账号')
    ldap_password = db.Column(db.String(255), comment='LDAP密码')
    gerrit_url = db.Column(db.String(500), comment='Gerrit服务器地址')
    maintainer_name = db.Column(db.String(100), comment='维护者姓名')
    maintainer_email = db.Column(db.String(255), comment='维护者邮箱')
    github_username = db.Column(db.String(100), comment='GitHub用户名')
    github_token = db.Column(db.String(255), comment='GitHub Token')
    crp_token = db.Column(db.String(255), comment='CRP Token')
    crp_branch_id = db.Column(db.Integer, comment='CRP项目分支ID')
    crp_topic_type = db.Column(db.String(50), default='test', comment='CRP主题类型')
    crp_topic_members = db.Column(db.Text, comment='创建CRP主题时自动添加的成员账号（分号或逗号分隔的LDAP用户名）')
    https_proxy = db.Column(db.String(200), comment='HTTPS代理配置')
    local_repos_dir = db.Column(db.String(500), default='/tmp/deepin-autopack-repos', comment='本地仓库存储目录')
    ai_api_url = db.Column(db.String(500), comment='AI API地址 (OpenAI兼容)')
    ai_api_key = db.Column(db.String(255), comment='AI API密钥')
    ai_model = db.Column(db.String(100), comment='AI模型名称')
    ai_analysis_fingerprint = db.Column(db.String(64), comment='提交分析指纹，用于缓存')
    ai_analysis_result = db.Column(db.Text, comment='缓存的 AI 提交分析结果')
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    @classmethod
    def get_config(cls):
        """获取全局配置（单例）"""
        config = cls.query.first()
        if not config:
            # 如果不存在，创建默认配置
            config = cls(id=1)
            db.session.add(config)
            db.session.commit()
        return config
    
    def to_dict(self):
        """转换为字典（密码字段不返回明文）"""
        return {
            'id': self.id,
            'ldap_username': self.ldap_username,
            'gerrit_url': self.gerrit_url,
            'maintainer_name': self.maintainer_name,
            'maintainer_email': self.maintainer_email,
            'has_ldap_password': bool(self.ldap_password),
            'has_github_token': bool(self.github_token),
            'has_crp_token': bool(self.crp_token),
            'has_ai_api_key': bool(self.ai_api_key),
            'ai_api_url': self.ai_api_url,
            'ai_model': self.ai_model,
            'ai_analysis_fingerprint': self.ai_analysis_fingerprint,
            'updated_at': (self.updated_at.isoformat() + 'Z') if (self.updated_at and self.updated_at.tzinfo is None) else (self.updated_at.isoformat() if self.updated_at else None)
        }
    
    def __repr__(self):
        return f'<GlobalConfig {self.id}>'
