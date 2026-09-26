# frozen_string_literal: true

class Organization < ApplicationRecord
  DEFAULT_OFFSETS = [ -3, 0, 7 ].freeze
  DEFAULT_FRIENDLY_REMINDERS = {
    "before_due" => { "enabled" => true, "days" => 3 }.freeze,
    "on_due" => { "enabled" => true }.freeze,
    "overdue" => { "enabled" => true, "days" => 7 }.freeze
  }.freeze

  has_many :users, dependent: :destroy
  has_many :webhook_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy
  has_many :clients, dependent: :destroy
  has_many :invoices, dependent: :destroy
  has_many :conversations, dependent: :destroy
  has_many :integrations, dependent: :destroy

  validates :name, presence: true
  validates :daily_digest_hour, numericality: { greater_than_or_equal_to: 0, less_than_or_equal_to: 23 }

  def zone
    Time.find_zone(time_zone).presence || Time.find_zone("UTC")
  end

  def today
    Time.current.in_time_zone(zone).to_date
  end

  def friendly_reminders
    self.class.normalize_friendly_reminders(escalation_offsets)
  end

  # Enabled Friendly steps in send order: { key:, offset: } (signed days vs due date).
  def enabled_ladder
    reminders = friendly_reminders
    [
      (reminders.dig("before_due", "enabled") ? { key: "notice_minus_3", offset: -Integer(reminders.dig("before_due", "days")) } : nil),
      (reminders.dig("on_due", "enabled") ? { key: "due_today", offset: 0 } : nil),
      (reminders.dig("overdue", "enabled") ? { key: "nudge_plus_3", offset: Integer(reminders.dig("overdue", "days")) } : nil)
    ].compact
  end

  def ladder_offsets
    enabled_ladder.map { |row| row[:offset] }
  end

  def self.normalize_friendly_reminders(raw)
    return from_legacy_offsets(raw) if raw.is_a?(Array)

    source = raw.respond_to?(:to_h) ? raw.to_h.deep_stringify_keys : {}
    {
      "before_due" => numbered_slot(source["before_due"], default_days: 3, min: 1, max: 30),
      "on_due" => { "enabled" => flag(source["on_due"], default: true) },
      "overdue" => numbered_slot(source["overdue"], default_days: 7, min: 1, max: 90)
    }
  end

  def self.from_legacy_offsets(values)
    before, on_due, overdue = Array(values).first(3)
    {
      "before_due" => numbered_slot({ "enabled" => !before.nil?, "days" => before }, default_days: 3, min: 1, max: 30),
      "on_due" => { "enabled" => !on_due.nil? },
      "overdue" => numbered_slot({ "enabled" => !overdue.nil?, "days" => overdue }, default_days: 7, min: 1, max: 90)
    }
  end

  def self.numbered_slot(raw, default_days:, min:, max:)
    source = raw.respond_to?(:to_h) ? raw.to_h.deep_stringify_keys : {}
    raw_days = source["days"].presence || (raw.is_a?(Numeric) || raw.is_a?(String) ? raw : nil)
    days = Integer(raw_days.presence || default_days).abs
    days = default_days unless days.between?(min, max)
    { "enabled" => flag(source, default: true), "days" => days }
  rescue ArgumentError, TypeError
    { "enabled" => flag(source, default: true), "days" => default_days }
  end

  def self.flag(raw, default:)
    source = raw.respond_to?(:to_h) ? raw.to_h.deep_stringify_keys : {}
    return default unless source.key?("enabled")

    ActiveModel::Type::Boolean.new.cast(source["enabled"])
  end
  private_class_method :numbered_slot, :flag
end
