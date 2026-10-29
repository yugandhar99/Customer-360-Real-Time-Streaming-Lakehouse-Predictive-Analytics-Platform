variable "database_name" { type = string }
variable "bucket_name" { type = string }
variable "tags" { type = map(string) }

locals {
  # Explicit schemas. Do not add a crawler unless the event contract changes
  # and a human reviews the new columns. Partition keys stay year, month, day.
  # Adding a column is backward compatible for JSON. Changing a partition key
  # requires a new table rather than an in-place edit.
  metric_tables = {
    ltv_metrics = [
      { name = "user_id", type = "string" },
      { name = "total_ltv", type = "double" },
      { name = "event_count", type = "bigint" },
    ]
    funnel_metrics = [
      { name = "stage", type = "string" },
      { name = "user_count", type = "bigint" },
    ]
    retention_metrics = [
      { name = "total_users", type = "bigint" },
      { name = "retained_users", type = "bigint" },
      { name = "retention_rate", type = "double" },
    ]
    cohort_metrics = [
      { name = "cohort_day", type = "string" },
      { name = "user_count", type = "bigint" },
    ]
    churn_metrics = [
      { name = "user_id", type = "string" },
      { name = "event_count", type = "bigint" },
      { name = "purchase_count", type = "bigint" },
      { name = "is_at_risk", type = "bigint" },
    ]
    user_segments = [
      { name = "user_id", type = "string" },
      { name = "frequency", type = "bigint" },
      { name = "monetary", type = "double" },
      { name = "segment_id", type = "bigint" },
      { name = "segment_label", type = "string" },
    ]
  }
}

resource "aws_glue_catalog_database" "this" {
  name = var.database_name
  tags = var.tags
}

resource "aws_glue_catalog_table" "events" {
  name          = "events"
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                    = "TRUE"
    classification              = "json"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2024,2035"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "storage.location.template" = "s3://${var.bucket_name}/raw/events/year=$${year}/month=$${month}/day=$${day}/"
  }

  storage_descriptor {
    location      = "s3://${var.bucket_name}/raw/events/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "TRUE"
      }
    }

    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "user_id"
      type = "string"
    }
    columns {
      name = "event_type"
      type = "string"
    }
    columns {
      name = "amount"
      type = "double"
    }
    columns {
      name = "timestamp"
      type = "string"
    }
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
}

resource "aws_glue_catalog_table" "metrics" {
  for_each      = local.metric_tables
  name          = each.key
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "json"
  }

  storage_descriptor {
    location      = "s3://${var.bucket_name}/analytics/${each.key}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

output "database_name" {
  value = aws_glue_catalog_database.this.name
}
