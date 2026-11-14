"""Create PlantFlow core schema and users table."""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
    CREATE TABLE plants(id BIGSERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,code TEXT UNIQUE NOT NULL);
    CREATE TABLE products(id BIGSERIAL PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL DEFAULT 'pcs');
    CREATE TABLE inventory(plant_id BIGINT REFERENCES plants(id),product_id BIGINT REFERENCES products(id),on_hand INTEGER NOT NULL DEFAULT 0 CHECK(on_hand>=0),in_transit INTEGER NOT NULL DEFAULT 0 CHECK(in_transit>=0),PRIMARY KEY(plant_id,product_id));
    CREATE TABLE transfers(id BIGSERIAL PRIMARY KEY,number TEXT UNIQUE NOT NULL,source_id BIGINT REFERENCES plants(id),destination_id BIGINT REFERENCES plants(id),status TEXT NOT NULL,created_at TEXT NOT NULL,dispatched_at TEXT,received_at TEXT,notes TEXT DEFAULT '',carrier TEXT DEFAULT '',expected_at TEXT);
    CREATE TABLE transfer_items(id BIGSERIAL PRIMARY KEY,transfer_id BIGINT REFERENCES transfers(id),product_id BIGINT REFERENCES products(id),quantity INTEGER NOT NULL CHECK(quantity>0),received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty>=0 AND received_qty<=quantity),UNIQUE(transfer_id,product_id));
    CREATE TABLE events(id BIGSERIAL PRIMARY KEY,transfer_id BIGINT REFERENCES transfers(id),event_type TEXT NOT NULL,event_at TEXT NOT NULL,details TEXT DEFAULT '');
    CREATE TABLE stock_movements(id BIGSERIAL PRIMARY KEY,plant_id BIGINT REFERENCES plants(id),product_id BIGINT REFERENCES products(id),transfer_id BIGINT REFERENCES transfers(id),movement_type TEXT NOT NULL,quantity INTEGER NOT NULL,created_at TEXT NOT NULL,note TEXT DEFAULT '');
    CREATE INDEX idx_transfers_created_at ON transfers(created_at);
    CREATE INDEX idx_transfers_status ON transfers(status);
    CREATE INDEX idx_events_transfer_id ON events(transfer_id,id);
    CREATE INDEX idx_stock_movements_transfer_id ON stock_movements(transfer_id);
    CREATE TABLE users(id BIGSERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','manager','viewer')),plant_id BIGINT REFERENCES plants(id),is_active BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
    CREATE INDEX idx_users_plant_id ON users(plant_id);
    """)
def downgrade():
    op.execute("DROP TABLE users,stock_movements,events,transfer_items,transfers,inventory,products,plants CASCADE")
