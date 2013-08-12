# -*- coding: utf-8 -*-

from django import template

register = template.Library()


@register.inclusion_tag('workflow/submit_line.html', takes_context=True)
def workflow_model_submit_row(context):
    """
    Displays the row of buttons for delete and save.
    """
    opts = context['opts']
    change = context['change']
    is_popup = context['is_popup']
    save_as = context['save_as']
    has_content_admin_permission = context.get(
        'has_content_admin_permission', True)
    has_content_manager_permission = context.get(
        'has_content_manager_permission', False)
    can_be_branched = context.get('can_be_branched', True)
    change_status_only = context.get('change_status_only', False)
    working_with_version = context.get('working_with_version', False)
    has_children = context.get('has_children', False)
    is_approved = context.get('is_approved', False)
    is_recovering = context.get('is_recovering', False)
    is_pending = context.get('is_pending', False)
    show_manager_extra = has_content_manager_permission \
        and change \
        and can_be_branched

    result = {
        'onclick_attrib': (opts.get_ordered_objects() and change
                           and 'onclick="submitOrderForm();"' or ''),
        'is_recovering': is_recovering,
        'is_popup': is_popup,
        'is_new': not change,
    }

    if is_recovering:
        result.update({
            'show_delete_link': False,
            'show_save_as_new': False,
            'show_save_and_add_another': False,
            'show_save_and_continue': False,
            'show_save': False,
            'show_save_to_history': False,
            'show_send_to_approve': False,
            'show_change_status': False,
        })
    else:
        result.update({
            'show_delete_link': (not is_popup and has_content_admin_permission
                and (change or context.get('show_delete', False))) \
                and not has_children and not is_approved,
            'delete_url': context.get('delete_url', 'delete/'),

            'show_save_as_new': not is_popup and save_as and change
                and not change_status_only,
            'show_save_and_add_another': context['has_add_permission'] and
                not is_popup and (not save_as or context['add']) and
                (not change or can_be_branched) and not change_status_only,
            'show_save_and_continue': not is_popup and context['has_change_permission'] and
                (not change or can_be_branched) and not change_status_only,
            'show_save': ((has_content_admin_permission and can_be_branched
                and not change_status_only and not is_pending) or not change),

            'show_save_to_history': (show_manager_extra or has_content_admin_permission)
                and not change_status_only and can_be_branched,
            'save_style': '' if (has_content_admin_permission and change) else 'default',
            'show_send_to_approve': show_manager_extra,
            'show_change_status': working_with_version and has_content_admin_permission
                and is_pending,
            'can_be_branched': can_be_branched,
        })
    return result
