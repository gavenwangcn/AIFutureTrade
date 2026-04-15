-- 盯盘策略：保存用于代码校验/测试的合约符号（与前端 validate_symbol / 生成代码时 symbol 一致）
ALTER TABLE strategys
  ADD COLUMN validate_symbol VARCHAR(64) NULL COMMENT '盯盘策略校验用合约符号，如 BTC、BTCUSDT' AFTER type;
