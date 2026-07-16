"""
仓库管理服务
处理 Git 仓库的克隆和更新
"""

import os
import subprocess
import threading
from git import Repo, GitCommandError
from app import db
from app.models import Project, GlobalConfig
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class RepoService:
    """仓库管理服务"""
    
    @staticmethod
    def _clone_project_in_context(project_id: int):
        """
        在 app context 中同步克隆单个项目仓库（实际克隆逻辑）。

        由 clone_project_repo / clone_all_repos 复用。

        Args:
            project_id: 项目ID
        """
        try:
            project = Project.query.get(project_id)
            if not project:
                logger.error(f"项目 {project_id} 不存在")
                return

            # 更新状态为克隆中
            project.repo_status = 'cloning'
            db.session.commit()

            logger.info(f"开始克隆项目 {project.name} 的仓库...")

            # 获取全局配置
            config = GlobalConfig.get_config()
            repos_dir = config.local_repos_dir if config and config.local_repos_dir else '/tmp/deepin-autopack-repos'

            # 创建目录
            os.makedirs(repos_dir, exist_ok=True)

            # 确定本地路径
            local_path = os.path.join(repos_dir, project.name)

            # 如果目录已存在，先删除
            if os.path.exists(local_path):
                import shutil
                shutil.rmtree(local_path)

            # rmtree 可能把被构建任务 os.chdir 占用的进程当前目录删掉，
            # 而 GitPython 的 clone_from 依赖 os.getcwd()，会抛 FileNotFoundError。
            # 这里在克隆前校验并修正进程 CWD 到刚创建好的 repos_dir。
            try:
                os.getcwd()
            except OSError:
                logger.warning("进程当前目录已失效，切换到 repos_dir 后重试克隆")
                os.chdir(repos_dir)

            # 确定克隆URL和仓库类型
            # 优先级：github_url > gerrit_repo_url（GitHub 优先）
            # 根据 URL 内容判断是否为 GitHub 仓库
            clone_url = None
            is_github = False

            if project.github_url:
                clone_url = project.github_url
                is_github = True
                logger.info(f"使用 GitHub 仓库: {clone_url}")
            elif project.gerrit_repo_url:
                clone_url = project.gerrit_repo_url
                # 仍然检查是否为 GitHub URL
                if 'github.com' in clone_url.lower():
                    is_github = True
                    logger.info(f"使用 GitHub 仓库: {clone_url}")
                else:
                    logger.info(f"使用 Gerrit 仓库: {clone_url}")
            else:
                raise Exception("未配置仓库地址")

            # 配置代理（只在克隆 GitHub 仓库时使用）
            env = os.environ.copy()
            if is_github and config and config.https_proxy:
                env['https_proxy'] = config.https_proxy
                env['http_proxy'] = config.https_proxy
                logger.info(f"GitHub 仓库使用代理: {config.https_proxy}")
            elif not is_github:
                logger.info("Gerrit 仓库不使用代理")

            # 确定分支
            branch = project.github_branch if is_github else project.gerrit_branch

            # 克隆仓库
            logger.info(f"克隆到: {local_path}，分支: {branch}")
            repo = Repo.clone_from(
                clone_url,
                local_path,
                branch=branch,
                env=env
            )

            # 更新项目信息
            project.local_repo_path = local_path
            project.repo_status = 'ready'
            project.repo_error = None
            db.session.commit()

            logger.info(f"✓ 项目 {project.name} 仓库克隆成功")

        except GitCommandError as e:
            logger.error(f"Git 克隆失败: {str(e)}")
            project = Project.query.get(project_id)
            if project:
                project.repo_status = 'error'
                project.repo_error = f"Git克隆失败: {str(e)}"
                db.session.commit()

        except Exception as e:
            logger.error(f"克隆仓库异常: {str(e)}", exc_info=True)
            project = Project.query.get(project_id)
            if project:
                project.repo_status = 'error'
                project.repo_error = str(e)
                db.session.commit()

    @staticmethod
    def clone_project_repo(project_id: int):
        """
        异步克隆项目仓库

        Args:
            project_id: 项目ID
        """
        def _clone():
            # 需要在新线程中创建新的 app context
            from app import create_app
            app = create_app()

            with app.app_context():
                RepoService._clone_project_in_context(project_id)

        # 启动后台线程
        thread = threading.Thread(target=_clone)
        thread.daemon = True
        thread.start()

    @staticmethod
    def clone_all_repos(project_ids: Optional[List[int]] = None):
        """
        异步顺序重新克隆多个项目仓库。

        一次只克隆一个仓库，避免并发克隆造成资源争用或网络阻塞。
        调用方通常会先把所有项目状态置为 cloning，后台线程再逐个执行。

        Args:
            project_ids: 要克隆的项目ID列表，为 None 时克隆所有项目
        """
        def _clone_all():
            from app import create_app
            app = create_app()

            with app.app_context():
                ids = project_ids
                if ids is None:
                    projects = Project.query.all()
                    ids = [p.id for p in projects]

                logger.info(f"开始批量克隆 {len(ids)} 个项目仓库...")
                for pid in ids:
                    RepoService._clone_project_in_context(pid)
                logger.info("批量克隆任务执行完毕")

        # 启动后台线程
        thread = threading.Thread(target=_clone_all)
        thread.daemon = True
        thread.start()
    
    @staticmethod
    def get_commit_message(project: Project, commit_hash: str) -> str:
        """
        从本地仓库获取 commit message
        
        Args:
            project: 项目对象
            commit_hash: commit hash
            
        Returns:
            commit message 的第一行，失败返回空字符串
        """
        if not project.local_repo_path or not os.path.exists(project.local_repo_path):
            return ''
        
        try:
            repo = Repo(project.local_repo_path)
            commit = repo.commit(commit_hash)
            message = commit.message.strip()
            # 返回第一行作为 subject
            subject = message.split('\n')[0] if message else ''
            return subject
        except Exception as e:
            logger.error(f"获取 commit message 失败: {str(e)}")
            return ''
    
    @staticmethod
    def update_repo(project: Project):
        """
        更新本地仓库
        
        Args:
            project: 项目对象
        """
        if not project.local_repo_path or not os.path.exists(project.local_repo_path):
            logger.warning(f"项目 {project.name} 本地仓库不存在，需要先克隆")
            return False
        
        try:
            logger.info(f"更新项目 {project.name} 的本地仓库...")
            repo = Repo(project.local_repo_path)
            
            # 判断是否为 GitHub 仓库
            is_github = False
            remote_url = repo.remotes.origin.url
            if 'github.com' in remote_url.lower():
                is_github = True
            
            # 配置代理（只在 GitHub 仓库时使用）
            config = GlobalConfig.get_config()
            if is_github and config and config.https_proxy:
                with repo.config_writer() as git_config:
                    git_config.set_value('http', 'proxy', config.https_proxy)
                logger.info(f"GitHub 仓库使用代理更新")
            
            # 拉取最新代码
            origin = repo.remotes.origin
            origin.fetch()
            
            # 切换到指定分支并拉取
            branch = project.github_branch if is_github else project.gerrit_branch
            repo.git.checkout(branch)
            origin.pull()
            
            logger.info(f"✓ 项目 {project.name} 仓库更新成功")
            return True
            
        except Exception as e:
            logger.error(f"更新仓库失败: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def get_latest_tag(project: Project) -> Optional[str]:
        """
        获取仓库最新的 tag（优化版本，使用 git 命令）
        
        Args:
            project: 项目对象
            
        Returns:
            最新的 tag 名称，没有则返回 None
        """
        if not project.local_repo_path or not os.path.exists(project.local_repo_path):
            return None
        
        try:
            # 使用 git 命令直接获取最新 tag，比 GitPython 的 sorted 快很多
            result = subprocess.run(
                ['git', 'describe', '--tags', '--abbrev=0'],
                cwd=project.local_repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            
            # 如果上面的命令失败（例如没有 tag），尝试获取所有 tag 中最新的一个
            result = subprocess.run(
                ['git', 'tag', '--sort=-creatordate'],
                cwd=project.local_repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                tags = result.stdout.strip().split('\n')
                return tags[0] if tags else None
            
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"获取最新 tag 超时: {project.name}")
            return None
        except Exception as e:
            logger.error(f"获取最新 tag 失败: {str(e)}")
            return None
    
    @staticmethod
    def get_commits_since(project: Project, since_commit: str) -> Tuple[int, List[Dict]]:
        """
        获取从指定 commit 到 HEAD 的所有提交
        
        Args:
            project: 项目对象
            since_commit: 起始 commit hash 或 tag 名称
            
        Returns:
            (提交数量, 提交列表) 元组
            提交列表每项包含: hash, message, author, date
        """
        if not project.local_repo_path or not os.path.exists(project.local_repo_path):
            return 0, []
        
        try:
            repo = Repo(project.local_repo_path)
            
            # 获取当前分支
            branch = project.github_branch if 'github' in (project.github_url or '') else project.gerrit_branch
            
            # 获取从 since_commit 到当前分支的提交
            commits = list(repo.iter_commits(f'{since_commit}..{branch}'))
            
            commit_list = []
            for commit in commits:
                commit_list.append({
                    'hash': commit.hexsha[:8],
                    'full_hash': commit.hexsha,
                    'message': commit.message.strip().split('\n')[0],  # 只取第一行
                    'author': commit.author.name,
                    'date': commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            return len(commits), commit_list
            
        except Exception as e:
            logger.error(f"获取提交列表失败: {str(e)}")
            return 0, []
    
    @staticmethod
    def get_commits_since_tag(project: Project, tag: str) -> Tuple[int, List[Dict]]:
        """
        获取从指定 tag 到 HEAD 的所有提交（兼容旧接口）
        
        Args:
            project: 项目对象
            tag: tag 名称
            
        Returns:
            (提交数量, 提交列表) 元组
        """
        return RepoService.get_commits_since(project, tag)
    
    @staticmethod
    def get_latest_commit(project: Project) -> Optional[Dict]:
        """
        获取仓库最新提交信息
        
        Args:
            project: 项目对象
            
        Returns:
            包含 hash, message, author, date 的字典，失败返回 None
        """
        if not project.local_repo_path or not os.path.exists(project.local_repo_path):
            return None
        
        try:
            repo = Repo(project.local_repo_path)
            
            # 获取当前分支
            branch = project.github_branch if 'github' in (project.github_url or '') else project.gerrit_branch
            
            # 获取最新提交
            commit = repo.commit(branch)
            
            return {
                'hash': commit.hexsha[:8],
                'full_hash': commit.hexsha,
                'message': commit.message.strip().split('\n')[0],
                'author': commit.author.name,
                'date': commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"获取最新提交失败: {str(e)}")
            return None
