CREATE TABLE refund_links (
    refund_tx_id BIGINT PRIMARY KEY REFERENCES transactions (id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    original_tx_id BIGINT NOT NULL REFERENCES transactions (id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    CHECK (refund_tx_id <> original_tx_id)
);
CREATE INDEX idx_refund_links_original ON refund_links (original_tx_id);
UPDATE alembic_version SET version_num = '0022' WHERE version_num = '0021';
