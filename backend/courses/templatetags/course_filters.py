# courses/templatetags/course_filters.py
from django import template

register = template.Library()

@register.filter
def range_filter(value):
    """Create a range for template loops"""
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)

@register.filter
def stars_display(rating):
    """Display star rating"""
    try:
        rating = int(rating)
        stars = '⭐' * rating + '☆' * (5 - rating)
        return stars
    except (ValueError, TypeError):
        return '☆☆☆☆☆'

@register.filter 
def make_list(value):
    """Convert string to list for iteration"""
    return list(str(value))