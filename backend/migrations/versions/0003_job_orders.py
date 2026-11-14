"""Add external parent-build job order import and SFG transfer linkage."""
from alembic import op

revision = "0003_job_orders"
down_revision = "0002_security_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE job_orders (
            job_order_id TEXT PRIMARY KEY,
            parent_build TEXT NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit TEXT NOT NULL DEFAULT 'pcs',
            status TEXT NOT NULL DEFAULT 'OPEN',
            payload JSONB NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE job_order_events (
            id BIGSERIAL PRIMARY KEY,
            job_order_id TEXT NOT NULL REFERENCES job_orders(job_order_id),
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT ''
        )
    """)
    op.execute("ALTER TABLE transfers ADD COLUMN job_order_id TEXT REFERENCES job_orders(job_order_id)")
    op.execute("CREATE INDEX idx_transfers_job_order_id ON transfers(job_order_id)")
    op.execute("CREATE INDEX idx_job_order_events_job_order_id ON job_order_events(job_order_id)")


def downgrade():
    op.execute("ALTER TABLE transfers DROP COLUMN job_order_id")
    op.execute("DROP TABLE job_order_events")
    op.execute("DROP TABLE job_orders")
