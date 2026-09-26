# frozen_string_literal: true

# Settings::Update Interactor
# Purpose: persist org timezone and Friendly cadence preferences.
# Methods:
# - execute

class Settings::Update
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(organization:, attrs:)
    new(organization: organization, attrs: attrs).execute
  end

  def initialize(organization:, attrs:)
    @organization = organization
    @attrs = (attrs || {}).to_h.with_indifferent_access
  end

  def execute
    execute_log_and_return_open_struct do
      raise_string_error("Organization is required") if organization.blank?

      organization.assign_attributes(permitted)
      raise_string_error(organization.errors.full_messages.to_sentence) unless organization.save

      Settings::Serialize.payload(organization)
    end
  end

  private

  attr_reader :organization, :attrs

  def permitted
    out = {}
    out[:time_zone] = resolved_time_zone if time_zone_value.present?
    out[:friendly_auto_send] = cast_bool(attrs[:friendly_auto_send]) unless attrs[:friendly_auto_send].nil?
    out[:daily_digest_enabled] = cast_bool(attrs[:daily_digest_enabled]) unless attrs[:daily_digest_enabled].nil?
    out[:daily_digest_hour] = attrs[:daily_digest_hour] unless attrs[:daily_digest_hour].nil?
    out[:escalation_offsets] = normalized_reminders if reminder_attrs?
    out
  end

  def time_zone_value
    attrs[:time_zone].presence || attrs[:daily_digest_timezone].presence
  end

  def resolved_time_zone
    zone = time_zone_value.to_s.strip
    raise_string_error("Unknown timezone") if Time.find_zone(zone).blank?

    zone
  end

  def reminder_attrs?
    attrs.key?(:friendly_reminders) || attrs.key?(:escalation_offsets)
  end

  def normalized_reminders
    raw = attrs[:friendly_reminders].presence || attrs[:escalation_offsets]
    Organization.normalize_friendly_reminders(raw)
  rescue ArgumentError, TypeError
    raise_string_error("Friendly reminders are invalid")
  end

  def cast_bool(value)
    ActiveModel::Type::Boolean.new.cast(value)
  end
end
