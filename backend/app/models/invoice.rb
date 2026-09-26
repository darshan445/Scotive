# frozen_string_literal: true

class Invoice < ApplicationRecord
  BOOKS_STATUSES = %w[open partial paid voided].freeze
  CHASE_STATUSES = %w[watching needs_you stopped].freeze
  OPEN_BOOKS = %w[open partial].freeze
  CLOSED_BOOKS = %w[paid voided].freeze

  belongs_to :organization
  belongs_to :integration
  belongs_to :client
  belongs_to :last_human_inbound_message, class_name: "Message", optional: true
  has_many :invoice_conversations, dependent: :destroy
  has_many :conversations, through: :invoice_conversations
  has_many :invoice_chase_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy

  validates :external_id, :invoice_number, :issue_date, :due_date, presence: true
  validates :books_status, inclusion: { in: BOOKS_STATUSES }
  validates :chase_status, inclusion: { in: CHASE_STATUSES }

  scope :books_open, -> { where(books_status: OPEN_BOOKS).where("balance_remaining > 0") }

  def books_open?
    OPEN_BOOKS.include?(books_status) && balance_remaining.to_d.positive?
  end

  def books_closed?
    CLOSED_BOOKS.include?(books_status) || balance_remaining.to_d <= 0
  end

  def sleeping?
    expected_pay_date.present? && expected_pay_date >= Date.current
  end

  def wait_expired?
    expected_pay_date.present? && expected_pay_date < Date.current
  end

  def cadence_allowed?
    books_open? && chase_status == "watching" && !sleeping? && last_human_inbound_at.blank? && !past_friendly_window?
  end

  def days_late(today = organization&.today || Date.current)
    return 0 if due_date.blank?

    (today - due_date).to_i
  end

  # Silent + still on Friendly (due in the future, or today ≤ due + last Friendly offset).
  def past_friendly_window?(today = organization&.today || Date.current)
    offset = if organization
      Cadence::Steps.last_friendly_offset(organization)
    else
      Organization::DEFAULT_OFFSETS[Cadence::Steps::FRIENDLY.length - 1]
    end
    days_late(today) > offset
  end

  def list_bucket
    return "paid" if books_closed?
    return "stopped" if chase_status == "stopped"
    return "needs_you" if chase_status == "needs_you" || pending_approval_draft?
    return "needs_you" if last_human_inbound_at.present? && !sleeping?
    return "needs_you" if books_open? && !sleeping? && past_friendly_window?
    return "watching" if sleeping?

    "auto_reminders"
  end

  def pending_approval_draft?
    drafts = if outbox_messages.loaded?
      outbox_messages.select { |row| row.status == "draft" }
    else
      outbox_messages.where(status: "draft").to_a
    end
    drafts.any? { |row| Cadence::Steps.draft?(row.cadence_step) }
  end
end
