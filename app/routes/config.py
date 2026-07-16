from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import GlobalConfig
from app.services.crp_service import CRPService

import logging
logger = logging.getLogger(__name__)

config_bp = Blueprint('config', __name__, url_prefix='/config')

@config_bp.route('/api/config', methods=['GET'])
def get_config_api():
    """获取配置信息的API端点"""
    config = GlobalConfig.get_config()
    branch_name = CRPService.get_branch_name(config.crp_branch_id) if config.crp_branch_id else ''
    branch_options = CRPService.get_branch_options()
    return jsonify({
        'success': True,
        'data': {
            'crp_branch_id': config.crp_branch_id,
            'crp_branch_name': branch_name,
            'crp_branch_options': branch_options,
            'is_snipe_branch': config.crp_branch_id in (119, 123, 128),
            'crp_topic_type': config.crp_topic_type,
            'crp_topic_members': config.crp_topic_members or '',
            'ldap_username': config.ldap_username,
            'github_username': config.github_username,
            'maintainer_name': config.maintainer_name,
            'maintainer_email': config.maintainer_email,
            'ai_api_url': config.ai_api_url,
            'ai_model': config.ai_model,
            'has_ai_api_key': bool(config.ai_api_key)
        }
    })

@config_bp.route('/', methods=['GET', 'POST'])
def global_config():
    """全局配置页面"""
    config = GlobalConfig.get_config()
    
    if request.method == 'POST':
        try:
            # 更新配置
            config.ldap_username = request.form.get('ldap_username')
            config.gerrit_url = request.form.get('gerrit_url')
            config.maintainer_name = request.form.get('maintainer_name')
            config.maintainer_email = request.form.get('maintainer_email')
            config.local_repos_dir = request.form.get('local_repos_dir') or '/tmp/deepin-autopack-repos'
            config.https_proxy = request.form.get('https_proxy') or None
            
            # CRP配置
            crp_branch_id = request.form.get('crp_branch_id')
            if crp_branch_id:
                config.crp_branch_id = int(crp_branch_id)
            config.crp_topic_type = request.form.get('crp_topic_type') or 'test'
            config.crp_topic_members = request.form.get('crp_topic_members') or None
            
            # 只有当密码字段不为空时才更新密码
            ldap_password = request.form.get('ldap_password')
            if ldap_password:
                config.ldap_password = ldap_password
            
            # GitHub配置
            config.github_username = request.form.get('github_username')
            github_token = request.form.get('github_token')
            if github_token:
                config.github_token = github_token
            
            crp_token = request.form.get('crp_token')
            if crp_token:
                config.crp_token = crp_token

            # AI 配置
            config.ai_api_url = request.form.get('ai_api_url') or None
            config.ai_model = request.form.get('ai_model') or None
            ai_api_key = request.form.get('ai_api_key')
            if ai_api_key:
                config.ai_api_key = ai_api_key

            db.session.commit()
            flash('全局配置已保存！', 'success')
            return redirect(url_for('config.global_config'))
        except Exception as e:
            db.session.rollback()
            flash(f'保存失败: {str(e)}', 'danger')
    
    return render_template('config.html', config=config)

@config_bp.route('/test-gerrit', methods=['POST'])
def test_gerrit():
    """测试 Gerrit 连接（JSON API）"""
    from app.services.gerrit_service import create_gerrit_service
    
    config = GlobalConfig.get_config()
    
    # 检查是否是JSON请求
    is_json = request.is_json or request.headers.get('Content-Type') == 'application/x-www-form-urlencoded'
    
    if not config.ldap_username or not config.ldap_password or not config.gerrit_url:
        if is_json:
            return jsonify({'success': False, 'message': '请先配置 LDAP 账号和 Gerrit 地址'}), 400
        flash('请先配置 LDAP 账号和 Gerrit 地址', 'warning')
        return redirect(url_for('config.global_config'))
    
    try:
        # 创建 Gerrit 服务
        gerrit = create_gerrit_service(
            config.gerrit_url,
            config.ldap_username,
            config.ldap_password
        )
        
        # 测试项目名称（从表单获取）
        test_project = request.form.get('test_project', 'deepin-music')
        
        # 测试 API 调用
        result = gerrit.get_project_info(test_project)
        
        if result['success']:
            return jsonify({'success': True, 'message': f'项目 {test_project} 连接成功'})
        else:
            return jsonify({'success': False, 'message': result.get('message', '连接失败')})
    except Exception as e:
        return jsonify({'success': False, 'message': f'测试出错: {str(e)}'})

@config_bp.route('/test-crp', methods=['POST'])
def test_crp():
    """测试 CRP 连接（JSON API）"""
    import os
    import subprocess

    from app.services.crp_service import CRPService

    config = GlobalConfig.get_config()

    if not config.ldap_username or not config.ldap_password:
        return jsonify({'success': False, 'message': '请先配置 LDAP 账号和密码'}), 400

    def _refresh_token():
        """通过 LDAP 账号重新获取并缓存 Token，返回 (token, error_message)"""
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_dir, 'gen-crp-pwd.py')
        if not os.path.exists(script_path):
            return None, f'未找到加密脚本: {script_path}'
        result = subprocess.run(
            ['python3', script_path],
            input=config.ldap_password,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0 or not result.stdout:
            err = result.stderr.strip() if result.stderr else '密码加密失败'
            return None, err
        token = CRPService.fetch_token(config.ldap_username, result.stdout.strip())
        if not token:
            return None, 'CRP 登录失败，请检查 LDAP 账号密码'
        config.crp_token = token
        db.session.commit()
        return token, None

    # 优先用已缓存的 Token，缓存为空则实时获取
    token = config.crp_token
    if not token:
        token, err = _refresh_token()
        if not token:
            code = 500 if err and '未找到加密脚本' in err else 400
            return jsonify({'success': False, 'message': err}), code

    try:
        user = CRPService.fetch_user(token)
        # 缓存的 Token 已失效：用 LDAP 账号重新换取并重试一次
        if not user:
            logger.info('缓存的 CRP Token 已失效，尝试用 LDAP 账号重新获取...')
            token, err = _refresh_token()
            if not token:
                return jsonify({'success': False, 'message': err or 'CRP Token 无效或已过期'}), 400
            user = CRPService.fetch_user(token)
            if not user:
                return jsonify({'success': False, 'message': 'CRP Token 无效或已过期'}), 400

        if config.crp_branch_id:
            topics = CRPService.list_topics(
                token,
                config.ldap_username,
                config.crp_branch_id,
                config.crp_topic_type or 'test'
            )
            if topics:
                return jsonify({'success': True, 'message': f'CRP 连接成功，用户: {user}，找到 {len(topics)} 个主题'})
            else:
                return jsonify({'success': True, 'message': f'CRP 连接成功，用户: {user}，当前没有主题'})

        return jsonify({'success': True, 'message': f'CRP 连接成功，用户: {user}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'测试出错: {str(e)}'})

@config_bp.route('/refresh-crp-token', methods=['POST'])
def refresh_crp_token():
    """刷新 CRP Token"""
    import subprocess
    import os
    
    config = GlobalConfig.get_config()
    
    if not config.ldap_username or not config.ldap_password:
        return jsonify({'success': False, 'message': '请先配置 LDAP 账号和密码'}), 400
    
    try:
        # 使用项目中的 gen-crp-pwd.py 脚本
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_dir, 'gen-crp-pwd.py')
        
        if not os.path.exists(script_path):
            return jsonify({'success': False, 'message': f'未找到加密脚本: {script_path}'})
        
        # 执行脚本生成加密密码
        result = subprocess.run(
            ['python3', script_path],
            input=config.ldap_password,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout:
            # 脚本输出的是加密后的密码
            encrypted_password = result.stdout.strip()
            
            # 使用加密密码登录获取token
            from app.services.crp_service import CRPService
            new_token = CRPService.fetch_token(config.ldap_username, encrypted_password)
            
            if new_token:
                config.crp_token = new_token
                db.session.commit()
                return jsonify({'success': True, 'message': 'Token 刷新成功'})
            else:
                return jsonify({'success': False, 'message': 'CRP登录失败，请检查账号密码'})
        else:
            error_msg = result.stderr if result.stderr else '密码加密失败'
            return jsonify({'success': False, 'message': error_msg})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': '刷新超时，请稍后重试'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'刷新失败: {str(e)}'})


@config_bp.route('/test-ai', methods=['POST'])
def test_ai():
    """测试 AI API 连接"""
    import requests

    config = GlobalConfig.get_config()

    if not config.ai_api_url:
        return jsonify({'success': False, 'message': '请先配置 AI API 地址'}), 400
    if not config.ai_api_key:
        return jsonify({'success': False, 'message': '请先配置 AI API Key'}), 400

    try:
        model = config.ai_model or 'gpt-4o-mini'
        resp = requests.post(
            f"{config.ai_api_url.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return jsonify({'success': True, 'message': f'AI 连接成功 (模型: {model})'})
        else:
            detail = resp.text[:200]
            return jsonify({'success': False, 'message': f'API 返回 {resp.status_code}: {detail}'})
    except requests.Timeout:
        return jsonify({'success': False, 'message': '连接超时'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'连接失败: {str(e)}'})


