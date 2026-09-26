# frozen_string_literal: true

# Maps saved org Friendly slots onto cadence step keys.
# Offsets are days relative to due date: negative = before due, 0 = due day, positive = days late.
module Cadence::Steps
  LADDER = %w[notice_minus_3 due_today nudge_plus_3].freeze
  FRIENDLY = LADDER
  DRAFT = %w[firm_plus_7 urgent_plus_14 broken_promise].freeze
  ALL = (FRIENDLY + DRAFT).freeze
  FIRM = "firm_plus_7"
  FINAL = "urgent_plus_14"

  module_function

  def known?(step)
    ALL.include?(step.to_s)
  end

  def friendly?(step)
    FRIENDLY.include?(step.to_s)
  end

  def draft?(step)
    DRAFT.include?(step.to_s)
  end

  def default_ladder
    [
      { key: "notice_minus_3", offset: -3 },
      { key: "due_today", offset: 0 },
      { key: "nudge_plus_3", offset: 7 }
    ]
  end

  def enabled_ladder(organization)
    organization&.enabled_ladder.presence || default_ladder
  end

  # Last enabled Friendly offset (days vs due). Empty ladder = already past.
  def last_friendly_offset(organization)
    steps = organization ? organization.enabled_ladder : default_ladder
    return -1_000_000 if steps.blank?

    steps.last[:offset]
  end

  def ladder_rows(organization)
    today = organization.today
    enabled_ladder(organization).map do |row|
      {
        key: row[:key],
        offset: row[:offset],
        due_date: today - row[:offset],
        books_statuses: %w[open partial]
      }
    end
  end

  # Next enabled ladder step whose calendar date is strictly after today. Never rewinds.
  def next_future_step(organization, invoice)
    today = organization.today
    enabled_ladder(organization).each do |row|
      milestone = invoice.due_date + row[:offset]
      return { key: row[:key], date: milestone, offset: row[:offset] } if milestone > today
    end
    nil
  end

  def current_key(organization, invoice)
    days_late = (organization.today - invoice.due_date).to_i
    steps = enabled_ladder(organization)
    return FRIENDLY.first if steps.empty?

    matched = steps.first[:key]
    steps.each do |row|
      matched = row[:key] if days_late >= row[:offset]
    end
    matched
  end

  def offset_for(organization, step)
    row = enabled_ladder(organization).find { |entry| entry[:key] == step.to_s }
    return row[:offset] if row

    index = LADDER.index(step.to_s)
    index ? Organization::DEFAULT_OFFSETS.fetch(index) : 0
  end
end
