"""Add supporting indexes for common transfer searches."""
from alembic import op

revision = "0002_security_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE INDEX idx_transfer_items_product_id ON transfer_items(product_id)")
    op.execute("CREATE INDEX idx_transfers_source_id ON transfers(source_id)")
    op.execute("CREATE INDEX idx_transfers_destination_id ON transfers(destination_id)")

def downgrade():
    op.execute("DROP INDEX idx_transfer_items_product_id")
    op.execute("DROP INDEX idx_transfers_source_id")
    op.execute("DROP INDEX idx_transfers_destination_id")
