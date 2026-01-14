# Contributing

Thank you for considering contributing to this project!

## Development Setup

1. Fork the repository
2. Clone your fork
3. Install dependencies: `pip install -r requirements.txt`
4. Make your changes
5. Test thoroughly
6. Submit a pull request

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add comments for complex logic
- Keep functions focused and concise

## Pull Request Process

1. Update README.md if needed
2. Update CHANGELOG.md with your changes
3. Ensure all tests pass
4. Get approval from maintainer

## Reporting Issues

- Use GitHub Issues
- Provide clear description
- Include reproduction steps
- Add relevant logs/screenshots

## Questions?

Open an issue for discussion.
docker run --rm -it --net=container:aifuturetrade-async-service alpine sh -c "apk add iproute2 && watch -n 1 'ss -tunp | grep :443'"

http://156.254.6.176:5004/api/market-data/klines?symbol=MYXUSDT&interval=1d&limit=2
http://185.242.232.42:5004/api/market-data/klines?symbol=MYXUSDT&interval=1d&limit=2
docker stop $(docker ps -q --filter "name=buy-*")
docker rm $(docker ps -a -q -f "name=buy-*")
docker stop $(docker ps -q --filter "name=sell-*")
docker rm $(docker ps -a -q -f "name=sell-*")

cash = 初始资金 + 已实现盈亏 - 已用保证金（可用于新开仓的资金）
margin_used = Σ((持仓数量 × 开仓均价) / 杠杆倍数)（所有持仓占用的保证金）
positions_value = Σ(持仓数量 × 开仓均价)（持仓的开仓价值总和）
total_value = 初始资金 + 已实现盈亏 + 未实现盈亏（账户总价值）

