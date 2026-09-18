# frozen_string_literal: true

class WebhookEvent < ApplicationRecord
  belongs_to :organization, optional: true
  belongs_to :integration, optional: true
end
