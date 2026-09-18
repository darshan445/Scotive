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
    out[:follow_up_interval_days] = attrs[:follow_up_interval_days] if attrs[:follow_up_interval_days].present?
    out[:daily_digest_enabled] = cast_bool(attrs[:daily_digest_enabled]) unless attrs[:daily_digest_enabled].nil?
    out[:daily_digest_hour] = attrs[:daily_digest_hour] unless attrs[:daily_digest_hour].nil?
    out[:escalation_offsets] = normalized_offsets if attrs.key?(:escalation_offsets)
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

  def normalized_offsets
    values = Array(attrs[:escalation_offsets]).map { |value| Integer(value) }
    raise_string_error("Escalation offsets must be four numbers") unless values.size == 4

    values
  rescue ArgumentError, TypeError
    raise_string_error("Escalation offsets must be numbers")
  end

  def cast_bool(value)
    ActiveModel::Type::Boolean.new.cast(value)
  end
end
