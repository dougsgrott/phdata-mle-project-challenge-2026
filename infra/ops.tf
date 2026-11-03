# ---------------------------------------------------------------------------
# Alerts: alarms publish to this topic, which emails you
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

# AWS sends a confirmation email; nothing arrives until you click its link
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
# Alarms: each emails once when it fires and once when it recovers
# ---------------------------------------------------------------------------

# Any server-side failure seen by clients: app 500s and Lambda timeouts (504)
resource "aws_cloudwatch_metric_alarm" "server_errors" {
  alarm_name          = "${var.project}-api-server-errors"
  alarm_description   = "The API returned a 5XX error to a client"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = { ApiName = aws_api_gateway_rest_api.api.name, Stage = local.stage_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching" # no traffic is not a problem
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Warm requests take about 5 ms; p95 above 1 s means something is wrong
resource "aws_cloudwatch_metric_alarm" "slow_requests" {
  alarm_name          = "${var.project}-api-slow-requests"
  alarm_description   = "95% of Lambda requests in 5 minutes took longer than 1 second"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Fast cost guard: about 3 requests per second sustained for 5 minutes
resource "aws_cloudwatch_metric_alarm" "high_traffic" {
  alarm_name          = "${var.project}-api-high-traffic"
  alarm_description   = "More than 1,000 Lambda invocations in 5 minutes"
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# Budget: the slow backstop (billing data lags by hours). Covers the whole
# account, so any other spend in this account counts too.
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = "20"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # $5
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 25
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # $10
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # $20
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

# ---------------------------------------------------------------------------
# Saved Logs Insights queries (CloudWatch console > Logs Insights > Saved queries)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_query_definition" "latency" {
  name            = "${var.project}/latency-by-path"
  log_group_names = [aws_cloudwatch_log_group.api.name]
  query_string    = <<-QUERY
    fields @timestamp, path, latency_ms
    | filter ispresent(path)
    | stats count() as requests, pct(latency_ms, 50) as p50_ms, pct(latency_ms, 95) as p95_ms by path, bin(5m)
  QUERY
}

resource "aws_cloudwatch_query_definition" "client_and_server_errors" {
  name            = "${var.project}/errors-by-path-and-zipcode"
  log_group_names = [aws_cloudwatch_log_group.api.name]
  query_string    = <<-QUERY
    fields @timestamp, path, status, zipcode
    | filter ispresent(status) and status >= 400
    | stats count() as responses by path, status, zipcode
    | sort responses desc
  QUERY
}

resource "aws_cloudwatch_query_definition" "cold_starts" {
  name            = "${var.project}/cold-starts"
  log_group_names = [aws_cloudwatch_log_group.api.name]
  query_string    = <<-QUERY
    filter @type = "REPORT" and ispresent(@initDuration)
    | stats count() as cold_starts, avg(@initDuration) as avg_init_ms, max(@initDuration) as max_init_ms by bin(1h)
  QUERY
}