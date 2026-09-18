# frozen_string_literal: true

class Devise::JsonFailureApp < Devise::FailureApp
  def respond
    self.status = 401
    self.content_type = "application/json"
    self.response_body = {
      errors: [
        { status: "401", code: "unauthorized", detail: i18n_message }
      ]
    }.to_json
  end
end
