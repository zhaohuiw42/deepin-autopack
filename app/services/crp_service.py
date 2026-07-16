"""
CRP平台服务
处理与CRP平台的API交互
"""

import requests
import logging
import rsa
import base64
from typing import List, Dict, Optional
from app.models import GlobalConfig

logger = logging.getLogger(__name__)


class CRPService:
    """CRP平台服务类"""
    
    # CRP公钥用于密码加密
    CRP_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCkA9WqirWQII3D8/M9UG8X8ybQ
Ou+cPSNTgR9b4HenJ7A5zSfkXZnetb5q6MmKTJLGCl9MSsHveQPHmLGDG+xw2MlB
w3Yefd/jJ1Cg8pP69wlHRX+wiyh5p8KY55ehFNsQLm3kDGXgVJdtrZn/MiBOlCtE
fe9YvvT0lqy2BtBpaQIDAQAB
-----END PUBLIC KEY-----"""
    
    BASE_URL = "https://crp.uniontech.com/api"

    # 分支ID与分支名称的映射关系
    CRP_BRANCHES = {
        126: 'eagle-1076',
        128: 'snipe-2500u2',
        123: 'snipe-2500u1',
        119: 'snipe-2500',
        5: 'eagle-sp1',
        51: 'eagle-1043',
        47: 'eagle-1050',
    }

    @staticmethod
    def get_branch_name(branch_id: int) -> str:
        """根据分支ID获取分支名称"""
        return CRPService.CRP_BRANCHES.get(branch_id, str(branch_id))

    @staticmethod
    def get_branch_options() -> List[Dict]:
        """获取所有分支选项（下拉列表用）"""
        return [
            {'id': bid, 'name': bname}
            for bid, bname in sorted(CRPService.CRP_BRANCHES.items(), key=lambda x: x[1])
        ]
    
    @staticmethod
    def parse_members(value) -> List[str]:
        """将成员数据解析为去重后的纯账号列表

        支持多种 CRP 返回格式与用户输入：
        - 分号/逗号分隔的账号字符串："a;b,c"
        - 纯账号列表：["a", "b"]
        - CRP 用户对象列表：[{"name": "a", "namecn": "甲", ...}, ...]
        - 单个 CRP 用户对象：{"name": "a", ...}
        """
        if not value:
            return []
        names: List[str] = []
        if isinstance(value, dict):
            name = (value.get("name") or value.get("Name") or "").strip()
            if name:
                names.append(name)
            return names
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, dict):
                    name = (item.get("name") or item.get("Name") or "").strip()
                    if name and name not in names:
                        names.append(name)
                elif isinstance(item, str):
                    for part in item.replace(",", ";").split(";"):
                        n = part.strip()
                        if n and n not in names:
                            names.append(n)
                elif item is not None:
                    n = str(item).strip()
                    if n and n not in names:
                        names.append(n)
            return names
        if isinstance(value, str):
            for part in value.replace(",", ";").split(";"):
                n = part.strip()
                if n and n not in names:
                    names.append(n)
            return names
        return names

    @staticmethod
    def get_default_members() -> List[str]:
        """从全局配置读取创建主题时自动添加的默认成员"""
        config = GlobalConfig.get_config()
        return CRPService.parse_members(config.crp_topic_members)

    @staticmethod
    def _members_to_field(members) -> Optional[str]:
        """将成员列表转换为 CRP 接口所需的分号分隔字符串（空则 None）"""
        names = CRPService.parse_members(members)
        return ";".join(names) if names else None

    @staticmethod
    def encrypt_password(password: str) -> str:
        """
        使用RSA公钥加密密码
        
        Args:
            password: 明文密码
            
        Returns:
            Base64编码的加密密码
        """
        try:
            pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(
                CRPService.CRP_PUBLIC_KEY.encode()
            )
            cipher = rsa.encrypt(password.encode(), pub_key)
            return base64.b64encode(cipher).decode()
        except Exception as e:
            logger.error(f"密码加密失败: {str(e)}")
            raise
    
    @staticmethod
    def fetch_token(username: str, password: str) -> Optional[str]:
        """
        登录CRP平台获取Token
        
        Args:
            username: LDAP用户名
            password: LDAP密码（加密后）
            
        Returns:
            Token字符串，失败返回None
        """
        try:
            url = f"{CRPService.BASE_URL}/login"
            headers = {"Content-Type": "application/json"}
            data = {
                "userName": username,
                "password": password
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            token = result.get("Token", "")
            if not token:
                logger.error("Token not found in response")
                return None
            
            return token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"CRP登录失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"获取Token异常: {str(e)}")
            return None
    
    @staticmethod
    def get_token() -> Optional[str]:
        """
        从全局配置获取或刷新Token
        
        Returns:
            Token字符串，失败返回None
        """
        config = GlobalConfig.get_config()
        if not config.ldap_username or not config.ldap_password:
            logger.error("LDAP账号密码未配置")
            return None
        
        # 加密密码
        encrypted_pwd = CRPService.encrypt_password(config.ldap_password)
        
        # 获取token
        return CRPService.fetch_token(config.ldap_username, encrypted_pwd)
    
    @staticmethod
    def fetch_user(token: str) -> Optional[str]:
        """
        获取当前登录用户信息
        
        Args:
            token: CRP Token
            
        Returns:
            用户名，失败返回None
        """
        try:
            url = f"{CRPService.BASE_URL}/user"
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            return result.get("Name", "")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取用户信息失败: {str(e)}")
            return None
    
    @staticmethod
    def list_topics(token: str, username: str, branch_id: int, topic_type: str = "test",
                    include_abandoned: bool = False) -> List[Dict]:
        """
        获取主题列表
        
        Args:
            token: CRP Token
            username: 用户名（过滤）
            branch_id: 分支ID
            topic_type: 主题类型（test/release等）
            include_abandoned: 是否包含已放弃的主题，默认 False
            
        Returns:
            主题列表
        """
        try:
            url = f"{CRPService.BASE_URL}/topics/search"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "TopicType": "test",
                "UserName": username,
                "BranchID": branch_id
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            topics = response.json()
            # 默认过滤掉已放弃的主题，调用方可通过 include_abandoned 获取全部
            if not include_abandoned:
                topics = [t for t in (topics or []) if not t.get("Abandoned")]
            return topics
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取主题列表失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"获取主题列表异常: {str(e)}")
            return []
    

    @staticmethod
    def create_topic(token: str, name: str, branch_id: int, tpc_type: str = "public",
                     owner: str = "", description: str = "",
                     members=None) -> Optional[Dict]:
        """
        创建CRP主题

        Args:
            token: CRP Token
            name: 主题名称
            branch_id: 分支ID
            tpc_type: 公私有类型（private/public）
            owner: 主题所有者（LDAP用户名）
            description: 描述
            members: 主题成员账号列表（LDAP用户名），可选

        Returns:
            成功返回包含主题信息的字典，失败返回None
        """
        try:
            url = f"{CRPService.BASE_URL}/branches/{branch_id}/topics"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "Name": name,
                "BranchID": branch_id,
                "Type": "test",
                "TpcType": tpc_type,
                "Owner": owner,
                "Members": CRPService._members_to_field(members),
                "Description": description or name
            }

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()

            # CRP可能返回纯整数ID或JSON对象
            try:
                result = response.json()
                if isinstance(result, int):
                    topic_id = result
                    result = {"ID": topic_id}
                else:
                    topic_id = result.get("ID") or result.get("id", "")
            except (ValueError, AttributeError):
                topic_id = int(response.text.strip())
                result = {"ID": topic_id}
            logger.info(f"CRP主题创建成功: name={name}, id={topic_id}, tpc_type={tpc_type}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"创建CRP主题失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"创建CRP主题异常: {str(e)}")
            return None


    @staticmethod
    def list_all_topics(token: str, username: str, branch_id: int) -> List[Dict]:
        """
        获取所有类型的主题列表（test + public），合并去重
        
        Args:
            token: CRP Token
            username: 用户名（过滤）
            branch_id: 分支ID
            
        Returns:
            合并后的主题列表
        """
        all_topics = []
        seen_ids = set()
        for topic_type in ["test", "public"]:
            topics = CRPService.list_topics(token, username, branch_id, topic_type)
            for topic in topics:
                tid = topic.get("ID") or topic.get("id")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    all_topics.append(topic)
        return all_topics

    @staticmethod
    def get_topic_detail(token: str, topic_id: int) -> Optional[Dict]:
        """获取单个主题详情（含 Owner/Members 成员字段）

        Returns:
            标准化后的主题字典，失败返回 None
        """
        try:
            url = f"{CRPService.BASE_URL}/topics/{topic_id}"
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            raw = response.json()
            if not raw:
                return None
            return {
                "id": raw.get("ID") or raw.get("id"),
                "name": raw.get("Name") or raw.get("name", ""),
                "description": raw.get("Description") or raw.get("description", ""),
                "branch_id": raw.get("BranchID") or raw.get("branch_id"),
                "tpc_type": raw.get("TpcType") or raw.get("tpc_type", "public"),
                "owners": CRPService.parse_members(raw.get("Owner") or raw.get("owner")),
                "members": CRPService.parse_members(raw.get("Members") or raw.get("members")),
                "raw": raw,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"获取主题详情失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取主题详情异常: {str(e)}")
            return None

    @staticmethod
    def update_topic_members(token: str, topic_id: int,
                            owners=None, members=None) -> Optional[Dict]:
        """更新主题成员（Owner / Members）

        传入的 owners/members 为最终目标列表（整体覆盖）。为避免误清空，至少需保留
        一个 owner。成员为空时传 None 让 CRP 清空成员。

        Args:
            owners: 目标 owner 账号列表（整体覆盖）
            members: 目标 member 账号列表（整体覆盖）

        Returns:
            成功返回 True，失败返回 None
        """
        try:
            # 先取主题详情，补全 PUT 需要的完整 payload 字段
            detail = CRPService.get_topic_detail(token, topic_id)
            if not detail:
                logger.error(f"更新成员失败：无法获取主题 {topic_id} 详情")
                return None

            target_owners = CRPService.parse_members(owners) if owners is not None else detail["owners"]
            if not target_owners:
                logger.error("更新成员失败：主题至少需要一个 owner")
                return None
            target_members = CRPService.parse_members(members) if members is not None else detail["members"]

            raw = detail.get("raw") or {}
            url = f"{CRPService.BASE_URL}/topics/{topic_id}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            data = {
                "ID": raw.get("ID") or raw.get("id") or topic_id,
                "Name": raw.get("Name") or raw.get("name") or detail.get("name", ""),
                "TpcType": raw.get("TpcType") or raw.get("tpc_type") or detail.get("tpc_type", "public"),
                "Description": raw.get("Description") or raw.get("description") or detail.get("description", ""),
                "Type": raw.get("Type") or raw.get("type") or "test",
                "NameB64": raw.get("NameB64") or raw.get("name_b64"),
                "BranchID": raw.get("BranchID") or raw.get("branch_id") or detail.get("branch_id"),
                "SyncID": raw.get("SyncID") or raw.get("sync_id") or 0,
                "State": raw.get("State") or raw.get("state") or 0,
                "Owner": ";".join(target_owners),
                "Members": ";".join(target_members) if target_members else None,
                "Abandoned": bool(raw.get("Abandoned") or raw.get("abandoned") or False),
                "Completed": bool(raw.get("Completed") or raw.get("completed") or False),
                "RepoType": raw.get("RepoType") or raw.get("repo_type") or "deb",
            }

            response = requests.put(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            logger.info(f"更新主题成员成功: topic_id={topic_id}, owners={target_owners}, members={target_members}")
            return {
                "owners": target_owners,
                "members": target_members,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"更新主题成员失败: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"更新主题成员异常: {str(e)}")
            return None

    @staticmethod
    def list_topic_releases(token: str, topic_id: int) -> List[Dict]:
        """
        获取主题下的所有包（releases）
        
        Args:
            token: CRP Token
            topic_id: 主题ID
            
        Returns:
            包列表
        """
        try:
            url = f"{CRPService.BASE_URL}/topics/{topic_id}/releases"
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # 格式化返回数据
            releases = []
            for item in result:
                build_state = item.get("BuildState", {})
                releases.append({
                    'id': item.get("ID", 0),
                    'project_id': item.get("ProjectID", 0),
                    'project_name': item.get("ProjectName", ""),
                    'source_pkg_name': item.get("SourcePkgName", ""),
                    'branch': item.get("Branch", ""),
                    'tag': item.get("Tag", ""),
                    'commit': item.get("Commit", ""),
                    'build_id': item.get("BuildID", 0),
                    'build_state': build_state.get("state", "UNKNOWN"),
                    'arches': item.get("Arches", ""),
                })
            
            return releases
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取主题包列表失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"获取主题包列表异常: {str(e)}")
            return []
    
    @staticmethod
    def list_projects(token: str, project_name: str, branch_id: int) -> List[Dict]:
        """
        根据项目名和分支ID查询项目列表
        
        Args:
            token: CRP Token
            project_name: 项目名称
            branch_id: 分支ID
            
        Returns:
            项目列表，每个项目包含ID、Name、Branch等信息
        """
        try:
            url = f"{CRPService.BASE_URL}/project"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "page": 0,
                "perPage": 0,
                "projectGroupID": 0,
                "newCommit": False,
                "archived": False,
                "branchID": branch_id,
                "name": project_name
            }
            
            logger.info(f"调用CRP项目列表API: name={project_name}, branch_id={branch_id}")
            logger.debug(f"请求URL: {url}")
            logger.debug(f"请求数据: {data}")
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            projects = result.get('Projects', [])
            if projects is None:
                logger.warning(f"CRP返回的Projects字段为None，完整响应: {result}")
                return []
            
            logger.info(f"查询到{len(projects)}个匹配的项目: name={project_name}, branch_id={branch_id}")
            return projects if projects else []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"查询项目列表失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"查询项目列表异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    @staticmethod
    def delete_release(token: str, release_id: int) -> bool:
        """
        放弃一个包（删除release）
        
        Args:
            token: CRP Token
            release_id: Release ID
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            url = f"{CRPService.BASE_URL}/topic_releases/{release_id}"
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.delete(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            logger.info(f"成功删除release: {release_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"删除release失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"删除release异常: {str(e)}")
            return False
    
    @staticmethod
    def retry_build(token: str, release_id: int) -> bool:
        """
        重试构建一个包
        
        Args:
            token: CRP Token
            release_id: Release ID
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            url = f"{CRPService.BASE_URL}/topic_releases/{release_id}/retry"
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.post(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            logger.info(f"成功触发重试构建: {release_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"重试构建失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"重试构建异常: {str(e)}")
            return False
    
    @staticmethod
    def submit_build(token: str, topic_id: int, project_id: int, project_name: str,
                    branch: str, commit: str, tag: str, arches: str,
                    branch_id: int, changelog: str = "") -> Optional[Dict]:
        """
        提交CRP打包任务
        
        Args:
            token: CRP Token
            topic_id: 主题ID
            project_id: 项目ID
            project_name: 项目名称
            branch: 分支名称
            commit: commit hash
            tag: 版本tag
            arches: 架构列表，格式: "amd64;arm64;loong64"
            branch_id: CRP分支ID
            changelog: changelog信息
            
        Returns:
            成功返回包含build_id的字典，失败返回None
        """
        try:
            # 如果project_id为0，尝试自动解析
            resolved_project_id = project_id
            if project_id == 0:
                logger.info(f"========== 开始自动解析ProjectID ==========")
                logger.info(f"请求参数: project_name={project_name}, branch={branch}, branch_id={branch_id}")
                
                # 方法1: 先尝试从主题的已有release中找到项目ID
                releases = CRPService.list_topic_releases(token, topic_id)
                logger.info(f"从主题{topic_id}获取到{len(releases)}个release")
                for release in releases:
                    logger.debug(f"  Release: ProjectName={release.get('ProjectName')}, Branch={release.get('Branch')}, ProjectID={release.get('ProjectID')}")
                    if release.get('ProjectName') == project_name and release.get('Branch') == branch:
                        resolved_project_id = release.get('ProjectID', 0)
                        logger.info(f"✓ 从主题releases中找到ProjectID: {resolved_project_id}")
                        break
                
                # 方法2: 如果还是0，通过项目列表API查询
                if resolved_project_id == 0:
                    logger.info(f"从releases中未找到，尝试通过项目列表API查询...")
                    logger.info(f"查询参数: name={project_name}, branch_id={branch_id}")
                    projects = CRPService.list_projects(token, project_name, branch_id)
                    logger.info(f"项目列表API返回: {len(projects) if projects else 0}个项目")
                    if projects:
                        for proj in projects:
                            logger.info(f"  项目: ID={proj.get('ID')}, Name={proj.get('Name')}, Branch={proj.get('Branch')}")
                    if projects and len(projects) > 0:
                        resolved_project_id = projects[0].get('ID', 0)
                        logger.info(f"✓ 从项目列表中找到ProjectID: {resolved_project_id}")
                
                if resolved_project_id == 0:
                    logger.warning(f"✗ 无法自动解析ProjectID，将使用0（可能导致CRP返回500错误）")
                    logger.warning(f"   请检查: 1) 项目名称是否正确 2) 分支ID是否正确 3) CRP中是否存在此项目")
                logger.info(f"==========================================")
            
            url = f"{CRPService.BASE_URL}/topics/{topic_id}/new_release"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            # CRP不允许Tag中包含'-'字符，去掉Debian版本中'-'及后面的部分
            # 例如 1.0.0-1 -> 1.0.0, 2.3.4-5.1 -> 2.3.4
            safe_tag = tag.split('-')[0]
            if safe_tag != tag:
                logger.info(f"Tag已清洗: {tag} -> {safe_tag}")

            # 确保changelog是字符串，并放在列表中
            changelog_list = [changelog] if changelog else [""]
            
            data = {
                "Arches": arches,
                "BaseTag": None,
                "Branch": branch,
                "BuildID": 0,
                "BuildState": None,
                "Changelog": changelog_list,
                "Commit": commit,
                "History": None,
                "ID": 0,
                "ProjectID": resolved_project_id,
                "ProjectName": project_name,
                "ProjectRepoUrl": None,
                "SlaveNode": None,
                "Tag": safe_tag,
                "TagSuffix": None,
                "TopicID": topic_id,
                "TopicType": "test",
                "ChangeLogMode": True,
                "RepoType": "deb",
                "Custom": True,
                "BranchID": str(branch_id)
            }
            
            # 检查topic中是否已存在相同project和branch的release，如果存在则先删除
            # 使用模糊匹配，因为CRP中的项目名可能有后缀（如 dtk6log vs dtk6log-v25）
            existing_releases = CRPService.list_topic_releases(token, topic_id)
            for release in existing_releases:
                release_project = release.get('project_name', '')
                release_branch = release.get('branch', '')
                
                # 模糊匹配：release的项目名以我们的项目名开头，且分支相同
                if release_project.startswith(project_name) and release_branch == branch:
                    release_id = release.get('id')
                    logger.warning(f"发现匹配的release(模糊): id={release_id}, "
                                 f"project={release_project} (匹配 {project_name}), branch={branch}，将先删除")
                    if CRPService.delete_release(token, release_id):
                        logger.info(f"成功删除旧release: {release_id}")
                    else:
                        logger.warning(f"删除旧release失败: {release_id}，继续尝试创建新release")
                    break
            
            logger.info(f"准备提交CRP打包: ProjectID={resolved_project_id}, TopicID={topic_id}")
            logger.debug(f"请求数据: {data}")
            
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            # CRP成功时返回201 Created，响应内容是整数ID或JSON对象
            if response.status_code not in [200, 201]:
                logger.error(f"CRP API返回错误状态码: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                response.raise_for_status()
            
            # 解析响应 - 可能是整数ID或JSON对象
            try:
                result = response.json()
                # 如果响应是整数，直接作为build_id
                if isinstance(result, int):
                    build_id = result
                    logger.info(f"CRP打包任务提交成功: build_id={build_id}")
                else:
                    # 如果是JSON对象，从中提取ID
                    build_id = result.get('ID', 0)
                    logger.info(f"CRP打包任务提交成功: project={project_name}, commit={commit[:8]}")
                    logger.debug(f"CRP响应: {result}")
            except:
                # 如果JSON解析失败，尝试作为文本解析为整数
                try:
                    build_id = int(response.text.strip())
                    logger.info(f"CRP打包任务提交成功: build_id={build_id}")
                except:
                    logger.error(f"无法解析CRP响应: {response.text}")
                    build_id = 0
            
            # 构建返回结果
            return {
                'success': True,
                'build_id': build_id,
                'url': f"https://crp.uniontech.com/topics/{topic_id}",
                'message': '打包任务已提交'
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"提交CRP打包任务失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"提交CRP打包任务异常: {str(e)}")
            return None

    @staticmethod
    def get_topic_repo_urls(branch_id: int, topic_id: int) -> List[str]:
        """
        获取 CRP 主题构建产物对应的子仓库（apt 源）地址。

        调用 CRP 的 topic_urls 接口，返回 apt 源格式的地址列表：
            deb [trusted=yes] https://aptly.uniontech.com/.../  unstable main

        Args:
            branch_id: CRP 分支ID
            topic_id: CRP 主题ID

        Returns:
            apt 源地址字符串列表；无结果或失败时返回空列表
        """
        try:
            url = f"{CRPService.BASE_URL}/topic_urls"
            headers = {"Content-Type": "application/json"}
            data = {
                "branchID": branch_id,
                "topicID": topic_id,
            }

            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            result = response.json() or {}
            repo_urls = result.get("RepoUrls") or []
            return [f"deb [trusted=yes] {u} unstable main" for u in repo_urls]
        except requests.exceptions.RequestException as e:
            logger.error(f"获取CRP仓库地址失败: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"响应内容: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"获取CRP仓库地址异常: {str(e)}")
            return []

    @staticmethod
    def get_build_state_info(state: str) -> Dict[str, str]:
        """
        获取构建状态的显示信息
        
        Args:
            state: 构建状态
            
        Returns:
            包含label(显示文本)和badge_class(Bootstrap类名)的字典
        """
        state_upper = str(state).upper()
        
        state_map = {
            'UPLOAD_OK': {'label': '构建成功', 'badge_class': 'bg-success'},
            'SUCCESS': {'label': '成功', 'badge_class': 'bg-success'},
            'OK': {'label': '成功', 'badge_class': 'bg-success'},
            'UPLOAD_GIVEUP': {'label': '已放弃', 'badge_class': 'bg-danger'},
            'APPLY_FAILED': {'label': '申请失败', 'badge_class': 'bg-danger'},
            'APPLYING': {'label': '申请中', 'badge_class': 'bg-warning'},
            'UPLOADING': {'label': '上传中', 'badge_class': 'bg-warning'},
            'UNKNOWN': {'label': '未知', 'badge_class': 'bg-secondary'},
        }
        
        return state_map.get(state_upper, {
            'label': state,
            'badge_class': 'bg-secondary'
        })
