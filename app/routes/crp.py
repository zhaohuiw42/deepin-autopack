"""
CRP主题管理路由
"""

from flask import Blueprint, render_template, jsonify, request
from app.services.crp_service import CRPService
from app.models import GlobalConfig
import logging

logger = logging.getLogger(__name__)

crp_bp = Blueprint('crp', __name__)


@crp_bp.route('/topics')
def topics():
    """CRP主题列表页面"""
    return render_template('crp_topics.html')


@crp_bp.route('/topics/<int:topic_id>')
def topic_detail(topic_id):
    """CRP主题详情页面"""
    # 只返回空页面，数据通过API异步加载
    return render_template('crp_topic_detail.html', topic_id=topic_id)


@crp_bp.route('/api/topics/<int:topic_id>/detail', methods=['GET'])
def api_topic_detail(topic_id):
    """获取主题详情数据的API"""
    try:
        # 获取token
        token = CRPService.get_token()
        if not token:
            return jsonify({
                'success': False,
                'message': 'CRP登录失败，请检查LDAP账号密码'
            }), 401
        
        # 获取配置
        config = GlobalConfig.get_config()
        username = CRPService.fetch_user(token)
        
        # 获取主题信息
        topics = CRPService.list_all_topics(token, username, config.crp_branch_id)
        
        # 找到当前主题（API返回的字段名可能是大写ID或小写id）
        topic = None
        for t in topics:
            t_id = t.get('ID') or t.get('id')
            if t_id == topic_id:
                # 标准化字段名
                topic = {
                    'id': t.get('ID') or t.get('id'),
                    'name': t.get('Name') or t.get('name', ''),
                    'description': t.get('Description') or t.get('description', ''),
                    'create_time': t.get('CreateTime') or t.get('create_time', ''),
                    'creator_name': t.get('CreatorName') or t.get('creator_name', '')
                }
                break
        
        if not topic:
            return jsonify({
                'success': False,
                'message': '主题未找到'
            }), 404
        
        # 获取包列表
        releases = CRPService.list_topic_releases(token, topic_id)
        
        return jsonify({
            'success': True,
            'data': {
                'topic': topic,
                'releases': releases
            }
        })
        
    except Exception as e:
        logger.error(f"获取主题详情失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'获取主题详情失败: {str(e)}'
        }), 500


@crp_bp.route('/api/topics', methods=['GET'])
def api_get_topics():
    """获取主题列表API"""
    try:
        # 获取配置
        config = GlobalConfig.get_config()
        
        if not config.crp_branch_id:
            return jsonify({
                'success': False,
                'message': 'CRP分支ID未配置，请先在全局配置中设置'
            }), 400
        
        # 获取token
        token = CRPService.get_token()
        if not token:
            return jsonify({
                'success': False,
                'message': 'CRP登录失败，请检查LDAP账号密码'
            }), 401
        
        # 获取用户名
        username = CRPService.fetch_user(token)
        if not username:
            return jsonify({
                'success': False,
                'message': '获取用户信息失败'
            }), 500
        
        # 支持通过参数指定分支ID，否则使用全局配置
        branch_id = request.args.get('branch_id', type=int) or config.crp_branch_id
        topics = CRPService.list_all_topics(token, username, branch_id)
        
        return jsonify({
            'success': True,
            'data': topics
        })
        
    except Exception as e:
        logger.error(f"获取主题列表失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'获取主题列表失败: {str(e)}'
        }), 500



@crp_bp.route('/api/topics/create', methods=['POST'])
def api_create_topic():
    """创建CRP主题"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'message': '主题名称不能为空'}), 400

        description = data.get('description', '').strip()
        tpc_type = data.get('tpc_type', 'public').strip()

        config = GlobalConfig.get_config()
        branch_id = data.get('branch_id') or config.crp_branch_id
        if not branch_id:
            return jsonify({'success': False, 'message': 'CRP分支ID未配置'}), 400

        token = CRPService.get_token()
        if not token:
            return jsonify({'success': False, 'message': 'CRP登录失败'}), 401

        # 获取当前用户作为主题Owner
        owner = CRPService.fetch_user(token) or ""

        # 成员：请求体可选指定 members，再合并全局配置的默认成员（去重）
        members = []
        body_members = data.get('members') or []
        if isinstance(body_members, str):
            body_members = [m for m in body_members.replace(',', ';').split(';') if m.strip()]
        members.extend(CRPService.parse_members(body_members))
        members.extend(CRPService.get_default_members())
        # 去重保序
        members = CRPService.parse_members(members)

        result = CRPService.create_topic(
            token=token,
            name=name,
            branch_id=branch_id,
            tpc_type=tpc_type,
            owner=owner,
            description=description or name,
            members=members
        )

        if result:
            topic_id = result.get('ID') or result.get('id')
            member_msg = ''
            if members:
                # CRP 创建接口对 Members 字段不可靠（会被忽略），创建后用 PUT 显式补加。
                # 用纯账号 owner 双保险，避免依赖 CRP 返回的对象格式解析。
                upd = CRPService.update_topic_members(
                    token, int(topic_id), owners=[owner] if owner else None, members=members
                )
                if upd:
                    member_msg = f'，已自动添加成员：{"、".join(members)}'
                else:
                    member_msg = '，成员自动添加失败，请到主题详情页手动添加'
            return jsonify({
                'success': True,
                'data': {
                    'id': topic_id,
                    'name': result.get('Name') or result.get('name', name)
                },
                'message': f'主题 [{name}] 创建成功{member_msg}'
            })
        else:
            return jsonify({'success': False, 'message': '创建主题失败，请查看日志'}), 500

    except Exception as e:
        logger.error(f"创建主题失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'创建主题失败: {str(e)}'}), 500


@crp_bp.route('/api/topics/<int:topic_id>/members', methods=['GET'])
def api_topic_members(topic_id):
    """获取主题成员（owner/member）"""
    try:
        token = CRPService.get_token()
        if not token:
            return jsonify({'success': False, 'message': 'CRP登录失败，请检查LDAP账号密码'}), 401

        detail = CRPService.get_topic_detail(token, topic_id)
        if not detail:
            return jsonify({'success': False, 'message': '获取主题详情失败，可能无权限或主题不存在'}), 404

        return jsonify({
            'success': True,
            'data': {
                'owners': detail.get('owners', []),
                'members': detail.get('members', []),
                'name': detail.get('name', '')
            }
        })
    except Exception as e:
        logger.error(f"获取主题成员失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'获取主题成员失败: {str(e)}'}), 500


@crp_bp.route('/api/topics/<int:topic_id>/members', methods=['POST'])
def api_update_topic_members(topic_id):
    """更新主题成员（添加/移除 owner 或 member）

    请求体：
        add_members: [account, ...]      要添加的成员
        remove_members: [account, ...]   要移除的成员
        add_owners: [account, ...]       要添加的 owner
        remove_owners: [account, ...]    要移除的 owner
        set_members: [account, ...]      整体覆盖成员（可选）
        set_owners: [account, ...]      整体覆盖 owner（可选）
    """
    try:
        token = CRPService.get_token()
        if not token:
            return jsonify({'success': False, 'message': 'CRP登录失败，请检查LDAP账号密码'}), 401

        data = request.get_json(silent=True) or {}

        detail = CRPService.get_topic_detail(token, topic_id)
        if not detail:
            return jsonify({'success': False, 'message': '获取主题详情失败，可能无权限或主题不存在'}), 404

        owners = list(detail.get('owners', []))
        members = list(detail.get('members', []))

        if data.get('set_owners') is not None:
            owners = CRPService.parse_members(data.get('set_owners'))
        if data.get('set_members') is not None:
            members = CRPService.parse_members(data.get('set_members'))

        for acc in CRPService.parse_members(data.get('add_owners')):
            if acc not in owners:
                owners.append(acc)
        for acc in CRPService.parse_members(data.get('remove_owners')):
            owners = [o for o in owners if o != acc]
        for acc in CRPService.parse_members(data.get('add_members')):
            if acc not in members:
                members.append(acc)
        for acc in CRPService.parse_members(data.get('remove_members')):
            members = [m for m in members if m != acc]

        if not owners:
            return jsonify({'success': False, 'message': '主题至少需要保留一个 owner'}), 400

        result = CRPService.update_topic_members(token, topic_id, owners=owners, members=members)
        if result is None:
            return jsonify({'success': False, 'message': '更新成员失败，请查看日志'}), 500

        return jsonify({
            'success': True,
            'data': {
                'owners': result['owners'],
                'members': result['members']
            },
            'message': '成员更新成功'
        })
    except Exception as e:
        logger.error(f"更新主题成员失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'更新主题成员失败: {str(e)}'}), 500


@crp_bp.route('/api/topics/<int:topic_id>/releases', methods=['GET'])
def api_get_topic_releases(topic_id):
    """获取主题下的包列表API"""
    try:
        # 获取token
        token = CRPService.get_token()
        if not token:
            return jsonify({
                'success': False,
                'message': 'CRP登录失败，请检查LDAP账号密码'
            }), 401
        
        # 获取包列表
        releases = CRPService.list_topic_releases(token, topic_id)
        
        # 添加状态显示信息
        for release in releases:
            state_info = CRPService.get_build_state_info(release['build_state'])
            release['state_label'] = state_info['label']
            release['state_badge_class'] = state_info['badge_class']
        
        return jsonify({
            'success': True,
            'data': releases
        })
        
    except Exception as e:
        logger.error(f"获取包列表失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'获取包列表失败: {str(e)}'
        }), 500


@crp_bp.route('/api/releases/<int:release_id>', methods=['DELETE'])
def api_delete_release(release_id):
    """放弃包API"""
    try:
        # 获取token
        token = CRPService.get_token()
        if not token:
            return jsonify({
                'success': False,
                'message': 'CRP登录失败，请检查LDAP账号密码'
            }), 401
        
        # 删除release
        success = CRPService.delete_release(token, release_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '已成功放弃该包'
            })
        else:
            return jsonify({
                'success': False,
                'message': '放弃包失败'
            }), 500
        
    except Exception as e:
        logger.error(f"放弃包失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'放弃包失败: {str(e)}'
        }), 500


@crp_bp.route('/api/releases/<int:release_id>/retry', methods=['POST'])
def api_retry_build(release_id):
    """重试构建API"""
    try:
        # 获取token
        token = CRPService.get_token()
        if not token:
            return jsonify({
                'success': False,
                'message': 'CRP登录失败，请检查LDAP账号密码'
            }), 401
        
        # 重试构建
        success = CRPService.retry_build(token, release_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '已触发重新构建'
            })
        else:
            return jsonify({
                'success': False,
                'message': '重试构建失败'
            }), 500
        
    except Exception as e:
        logger.error(f"重试构建失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'重试构建失败: {str(e)}'
        }), 500
