"""Additive v1.1 catalogue, policies, scans and maintenance evidence."""

import sqlalchemy as sa
from alembic import context, op
from app import persistence as p
from app.catalogue import normalized

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FIELDS = [
    "title",
    "category",
    "video_quality",
    "audio_codecs",
    "audio_languages",
    "subtitle_languages",
    "file_size_bytes",
    "mtime_ns",
    "observed_size",
    "availability",
    "workflow_state",
    "last_seen",
    "revision",
]
TABLES = [p.policies, p.scans, p.maintenance_files, p.subtitle_versions, p.tombstones]


def upgrade() -> None:
    for name in FIELDS:
        col = p.assets.c[name]
        op.add_column(
            "library_assets",
            sa.Column(name, col.type, nullable=col.nullable, server_default=col.server_default),
        )
    for table in TABLES:
        table.create(op.get_bind())
    conn = op.get_bind()
    for row in conn.execute(sa.select(p.assets)).mappings():
        conn.execute(
            sa.update(p.assets)
            .where(p.assets.c.id == row["id"])
            .values(**normalized(row["relative_path"], row["data"]))
        )
    # RC1 tracked quarantine only in its manifest table. Preserve that workflow
    # during upgrade without probing or modifying any filesystem paths.
    conn.execute(
        sa.update(p.assets)
        .where(
            p.assets.c.id.in_(
                sa.select(p.quarantine.c.asset_id).where(p.quarantine.c.state == "QUARANTINED")
            )
        )
        .values(workflow_state="QUARANTINED")
    )
    op.execute(
        "CREATE INDEX ix_assets_browse ON library_assets(workflow_state, category, lower(title), id)"
    )
    op.execute("CREATE INDEX ix_assets_audio ON library_assets USING gin(audio_languages)")
    op.execute("CREATE INDEX ix_assets_codec ON library_assets USING gin(audio_codecs)")
    op.execute("CREATE INDEX ix_assets_subtitle ON library_assets USING gin(subtitle_languages)")
    op.execute("""CREATE FUNCTION library_catalogue_changed() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        INSERT INTO service_settings(key,value,revision) VALUES('library_catalogue_generation','{}',1)
        ON CONFLICT(key) DO UPDATE SET revision=service_settings.revision+1;
        RETURN NULL;
      END $$""")
    op.execute(
        "CREATE TRIGGER library_catalogue_changed AFTER INSERT OR UPDATE OR DELETE ON library_assets FOR EACH STATEMENT EXECUTE FUNCTION library_catalogue_changed()"
    )


def downgrade() -> None:
    if context.get_x_argument(as_dictionary=True).get("disposable") != "true":
        raise RuntimeError(
            "Downgrade requires disposable=true; restore backup for production rollback"
        )
    op.execute("DROP TRIGGER IF EXISTS library_catalogue_changed ON library_assets")
    op.execute("DROP FUNCTION IF EXISTS library_catalogue_changed()")
    for name in ["ix_assets_browse", "ix_assets_audio", "ix_assets_codec", "ix_assets_subtitle"]:
        op.drop_index(name)
    for table in reversed(TABLES):
        table.drop(op.get_bind())
    for name in reversed(FIELDS):
        op.drop_column("library_assets", name)
