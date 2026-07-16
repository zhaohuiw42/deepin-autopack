from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Project, GlobalConfig
from app.services.gerrit_service import create_gerrit_service, get_commit_message_from_git
from app.services.repo_service import RepoService
import logging
import os

project_bp = Blueprint('project', __name__)

# 配置日志
logger = logging.getLogger(__name__)

@project_bp.route('/projects')
def project_list():
    """项目列表页"""
    projects = Project.query.all()
    logger.info(f"=== 项目列表查询开始，共 {len(projects)} 个项目 ===")
    
    # 获取全局配置以访问 Gerrit
    config = GlobalConfig.get_config()
    logger.info(f"全局配置: config={config}, ldap_username={config.ldap_username if config else None}")
    
    # 为每个项目获取 commit message
    project_data = []
    for project in projects:
        project_info = {
            'project': project,
            'commit_message': None
        }
        
        # 直接从本地仓库获取 commit message
        if project.last_commit_hash and project.repo_status == 'ready':
            subject = RepoService.get_commit_message(project, project.last_commit_hash)
            if subject:
                project_info['commit_message'] = subject
        
        project_data.append(project_info)
    
    logger.info(f"\n=== 项目列表查询完成 ===\n")
    return render_template('project_list.html', project_data=project_data)

@project_bp.route('/projects/new', methods=['GET', 'POST'])
def project_create():
    """创建项目"""
    if request.method == 'POST':
        try:
            project = Project(
                name=request.form.get('name'),
                gerrit_url=request.form.get('gerrit_url'),
                gerrit_branch=request.form.get('gerrit_branch'),
                gerrit_repo_url=request.form.get('gerrit_repo_url') or None,
                github_url=request.form.get('github_url'),
                github_branch=request.form.get('github_branch'),
                last_commit_hash=request.form.get('last_commit_hash'),
                crp_project_name=request.form.get('crp_project_name') or None,
                repo_status='pending'
            )
            db.session.add(project)
            db.session.commit()
            
            # 启动后台克隆任务
            RepoService.clone_project_repo(project.id)
            
            flash(f'项目 {project.name} 创建成功！正在后台克隆仓库...', 'success')
            return redirect(url_for('project.project_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'创建失败: {str(e)}', 'danger')
    
    return render_template('project_form.html', project=None)

@project_bp.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
def project_edit(id):
    """编辑项目"""
    project = Project.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            project.name = request.form.get('name')
            project.gerrit_url = request.form.get('gerrit_url')
            project.gerrit_branch = request.form.get('gerrit_branch')
            project.gerrit_repo_url = request.form.get('gerrit_repo_url') or None
            project.github_url = request.form.get('github_url')
            project.github_branch = request.form.get('github_branch')
            project.last_commit_hash = request.form.get('last_commit_hash')
            project.crp_project_name = request.form.get('crp_project_name') or None
            
            db.session.commit()
            flash(f'项目 {project.name} 更新成功！', 'success')
            return redirect(url_for('project.project_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败: {str(e)}', 'danger')
    
    return render_template('project_form.html', project=project)

@project_bp.route('/projects/<int:id>/delete', methods=['POST'])
def project_delete(id):
    """删除项目"""
    try:
        project = Project.query.get_or_404(id)
        name = project.name
        db.session.delete(project)
        db.session.commit()
        flash(f'项目 {name} 已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败: {str(e)}', 'danger')
    
    return redirect(url_for('project.project_list'))


@project_bp.route('/projects/<int:id>/clone', methods=['POST'])
def project_clone_repo(id):
    """克隆项目仓库（支持强制重新克隆）"""
    try:
        project = Project.query.get_or_404(id)
        
        if project.repo_status == 'cloning':
            return jsonify({'success': False, 'message': '仓库正在克隆中，请稍候'}), 400
        
        # 允许重新克隆（会自动删除旧仓库）
        RepoService.clone_project_repo(project.id)
        
        return jsonify({'success': True, 'message': '已开始克隆仓库'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@project_bp.route('/projects/clone-all', methods=['POST'])
def project_clone_all():
    """一键重新克隆所有项目仓库"""
    try:
        projects = Project.query.all()
        if not projects:
            return jsonify({'success': False, 'message': '没有可克隆的项目'}), 400

        # 立即将所有项目标记为克隆中，给出即时反馈
        for project in projects:
            project.repo_status = 'cloning'
            project.repo_error = None
        db.session.commit()

        # 后台顺序克隆（每个仓库克隆完成后才进行下一个）
        RepoService.clone_all_repos([p.id for p in projects])

        return jsonify({
            'success': True,
            'message': f'已开始重新克隆 {len(projects)} 个项目仓库',
            'data': {'project_ids': [p.id for p in projects]}
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@project_bp.route('/projects/<int:id>/status', methods=['GET'])
def project_repo_status(id):
    """获取项目仓库状态"""
    try:
        project = Project.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'repo_status': project.repo_status,
                'repo_error': project.repo_error,
                'path': project.local_repo_path
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    project.last_commit_hash = data.get('last_commit_hash', project.last_commit_hash)
    
    db.session.commit()
    return jsonify({'message': 'Project updated successfully!'})

@project_bp.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Project deleted successfully!'})