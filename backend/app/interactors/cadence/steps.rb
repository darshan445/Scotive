# frozen_string_literal: true

# Maps saved org ladder offsets onto cadence step keys.
# Offsets are days relative to due date: negative = before due, 0 = due day, positive = days late.
module Cadence::Steps
  LADDER = %w[notice_minus_3 due_today nudge_plus_3 firm_plus_7].freeze
  FRIENDLY = %w[notice_minus_3 due_today nudge_plus_3].freeze
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

  def ladder_rows(organization)
    today = organization.today
    organization.ladder_offsets.each_with_index.map do |offset, index|
      {
        key: LADDER.fetch(index),
        offset: offset,
        due_date: today - offset,
        statuses: offset.positive? ? %w[overdue partially_paid] : %w[invoiced overdue partially_paid]
      }
    end
  end

  def current_key(organization, invoice)
    days_late = (organization.today - invoice.due_date).to_i
    offsets = organization.ladder_offsets
    return FINAL if days_late >= offsets.last + organization.follow_up_interval_days

    matched = LADDER.first
    LADDER.each_with_index do |key, index|
      matched = key if days_late >= offsets.fetch(index)
    end
    matched
  end
end
