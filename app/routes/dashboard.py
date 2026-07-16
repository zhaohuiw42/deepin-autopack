"""主页看板路由"""
from flask import Blueprint, render_template, jsonify
from app.models import Project
from app.models.build_task import BuildTask, _utc_iso
from app.services.build_task_service import BuildTaskService
from datetime import datetime, timedelta
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """主页看板"""
    return render_template('dashboard.html')


@dashboard_bp.route('/api/dashboard/summary')
def api_summary():
    """聚合看板数据（仅快速DB查询，不含git/API调用）"""
    try:
        # 1. 项目统计
        projects = Project.query.all()
        total_projects = len(projects)
        ready_projects = sum(1 for p in projects if p.repo_status == 'ready')
        error_projects = sum(1 for p in projects if p.repo_status == 'error')
        cloning_projects = sum(1 for p in projects if p.repo_status == 'cloning')

        # 2. 任务统计
        running_tasks = BuildTask.query.filter_by(status='running').count()
        pending_tasks = BuildTask.query.filter_by(status='pending').count()
        failed_tasks = BuildTask.query.filter_by(status='failed').count()
        success_tasks = BuildTask.query.filter_by(status='success').count()
        paused_tasks = BuildTask.query.filter_by(status='paused').count()
        cancelled_tasks = BuildTask.query.filter_by(status='cancelled').count()

        # 3. 最近任务列表（最近10条，纯DB查询）
        recent_tasks = BuildTask.query.order_by(
            BuildTask.created_at.desc()
        ).limit(10).all()
        recent_tasks_data = []
        for task in recent_tasks:
            recent_tasks_data.append({
                'id': task.id,
                'project_name': task.project_name,
                'version': task.version,
                'mode': task.package_mode,
                'status': task.status,
                'current_step': task.current_step,
                'created_at': _utc_iso(task.created_at),
                'completed_at': _utc_iso(task.completed_at),
                'error_message': task.error_message,
                'github_pr_url': task.github_pr_url,
                'crp_build_url': task.crp_build_url,
            })

        return jsonify({
            'success': True,
            'data': {
                'stats': {
                    'total_projects': total_projects,
                    'ready_projects': ready_projects,
                    'error_projects': error_projects,
                    'cloning_projects': cloning_projects,
                    'running_tasks': running_tasks,
                    'pending_tasks': pending_tasks,
                    'failed_tasks': failed_tasks,
                    'success_tasks': success_tasks,
                    'paused_tasks': paused_tasks,
                    'cancelled_tasks': cancelled_tasks,
                },
                'recent_tasks': recent_tasks_data,
            }
        })

    except Exception as e:
        logger.exception(f"获取看板数据失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取看板数据失败: {str(e)}'
        }), 500


@dashboard_bp.route('/api/dashboard/weekly-stats')
def api_weekly_stats():
    """近7天任务统计（用于图表）"""
    try:
        seven_days_ago = datetime.utcnow() - timedelta(days=6)
        tasks = BuildTask.query.filter(
            BuildTask.created_at >= seven_days_ago
        ).all()

        # 按日期分组统计
        daily = {}
        for i in range(7):
            day = (datetime.utcnow() - timedelta(days=6 - i)).strftime('%m/%d')
            daily[day] = {'total': 0, 'success': 0, 'failed': 0}

        for task in tasks:
            day_key = task.created_at.strftime('%m/%d')
            if day_key in daily:
                daily[day_key]['total'] += 1
                if task.status == 'success':
                    daily[day_key]['success'] += 1
                elif task.status in ('failed', 'cancelled'):
                    daily[day_key]['failed'] += 1

        labels = list(daily.keys())
        totals = [daily[d]['total'] for d in labels]
        successes = [daily[d]['success'] for d in labels]
        failures = [daily[d]['failed'] for d in labels]

        return jsonify({
            'success': True,
            'data': {
                'labels': labels,
                'totals': totals,
                'successes': successes,
                'failures': failures,
            }
        })

    except Exception as e:
        logger.exception(f"获取周统计失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
