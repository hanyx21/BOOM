class RiskManager:
    def __init__(self, balance, max_percent_per_trade, daily_drawdown_limit_percent, max_concurrent_trades):
        self.balance = balance
        self.max_percent_per_trade = max_percent_per_trade
        self.daily_drawdown_limit_percent = daily_drawdown_limit_percent
        self.max_concurrent_trades = max_concurrent_trades

    def calculate_position_size(self, selected_signal: str):
        """Calculate the position size based on available balance."""
        if selected_signal == 'hold':
            return self.balance * self.max_percent_per_trade / 2  # Smaller position if holding
        return self.balance * self.max_percent_per_trade

    def max_concurrent_reached(self, fake_exec) -> bool:
        """
        True if the number of *open* trades equals or exceeds the limit set in
        self.max_concurrent_trades.
        """
        return len(fake_exec.get_open_positions()) >= self.max_concurrent_trades
