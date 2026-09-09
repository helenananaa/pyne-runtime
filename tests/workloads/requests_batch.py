# ruff: noqa: F821
indicator("Requests")
higher = request.security("TEST:ASSET", "30S", "close")
lower = request.security_lower_tf("TEST:ASSET", "5S", "close")
plot(higher, "HTF")
plot(lower.size(), "LTF count")
plot(lower.last(), "LTF last")
plot(ta.sma(close, 3) - higher, "Spread")
