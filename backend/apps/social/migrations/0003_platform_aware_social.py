"""Generalise the social platform layer.

Three things happen here, in an order that never drops data:

1. `XAccount` is *renamed* to `SocialAccount` and given a `platform` column.
   Every existing row is an X row, so it is backfilled to `platform="x"`.
2. `SocialPost` gains `platform` (backfilled to "x") and `x_account` is
   renamed to `account`.
3. The two bare `unique=True` constraints become composite
   `(platform, external_id)` constraints. This is the actual bug fix: X and
   TikTok both issue numeric ids, so a bare id is not a natural key and
   could silently reject a legitimate post.

Hand-written rather than generated: `makemigrations` would have dropped and
recreated the table, discarding every linked account and post.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

PLATFORMS = [
    ("x", "X (Twitter)"),
    ("tiktok", "TikTok"),
    ("instagram", "Instagram"),
    ("youtube", "YouTube"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0002_alter_campaignparticipation_seller"),
        ("sellers", "0001_initial"),
        ("social", "0002_socialpost_updated_at"),
    ]

    operations = [
        # 1. Rename the model, preserving rows.
        migrations.RenameModel(old_name="XAccount", new_name="SocialAccount"),
        migrations.AddField(
            model_name="socialaccount",
            name="platform",
            field=models.CharField(
                choices=PLATFORMS, db_index=True, default="x", max_length=16
            ),
        ),
        # `related_name` changed from `x_accounts` to `social_accounts`.
        migrations.AlterField(
            model_name="socialaccount",
            name="seller",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="social_accounts",
                to="sellers.sellerprofile",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="socialaccount", unique_together=set()
        ),
        # 2. Posts become platform-aware.
        migrations.AddField(
            model_name="socialpost",
            name="platform",
            field=models.CharField(
                choices=PLATFORMS, db_index=True, default="x", max_length=16
            ),
        ),
        migrations.RenameField(
            model_name="socialpost", old_name="x_account", new_name="account"
        ),
        migrations.AlterUniqueTogether(name="socialpost", unique_together=set()),
        # 3. Composite uniqueness replaces the bare unique=True.
        migrations.AlterField(
            model_name="socialaccount",
            name="provider_user_id",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="socialpost",
            name="external_post_id",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AddConstraint(
            model_name="socialaccount",
            constraint=models.UniqueConstraint(
                fields=("platform", "provider_user_id"),
                name="social_account_unique_provider_user_per_platform",
            ),
        ),
        # A seller holds at most one account per platform.
        migrations.AddConstraint(
            model_name="socialaccount",
            constraint=models.UniqueConstraint(
                fields=("seller", "platform"),
                name="social_account_one_per_platform_per_seller",
            ),
        ),
        migrations.AddConstraint(
            model_name="socialpost",
            constraint=models.UniqueConstraint(
                fields=("platform", "external_post_id"),
                name="social_post_unique_external_id_per_platform",
            ),
        ),
    ]
