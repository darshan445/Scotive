# frozen_string_literal: true

module Api
  module V1
    class SettingsController < Api::V1::BaseController
      def show
        result = ::Settings::Show.execute(organization: current_organization)
        render_result(result)
      end

      def update
        result = ::Settings::Update.execute(organization: current_organization, attrs: settings_params)
        render_result(result)
      end

      def timezones
        result = ::Settings::Timezones.execute
        render_result(result)
      end

      private

      def settings_params
        params.permit(
          :time_zone,
          :daily_digest_timezone,
          :daily_digest_enabled,
          :daily_digest_hour,
          :friendly_auto_send,
          escalation_offsets: [],
          friendly_reminders: {
            before_due: [ :enabled, :days ],
            on_due: [ :enabled ],
            overdue: [ :enabled, :days ]
          }
        ).to_h
      end
    end
  end
end
