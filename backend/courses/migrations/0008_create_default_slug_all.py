from django.db import migrations

def create_all_category(apps, schema_editor):
    CourseCategory = apps.get_model('courses', 'CourseCategory')
    if not CourseCategory.objects.filter(slug="all").exists():
        CourseCategory.objects.create(
            name="All",
            description="Default category for uncategorized courses",
            slug="all",
            is_active=True,
            order=0
        )

class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0007_rename_courses_categor_33f89e_idx_courses_categor_2870c7_idx_and_more'),  # replace with your last migration name
    ]

    operations = [
        migrations.RunPython(create_all_category),
    ]
