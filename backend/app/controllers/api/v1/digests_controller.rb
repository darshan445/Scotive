# frozen_string_literal: true

module Api
  module V1
    class DigestsController < Api::V1::BaseController
      def today
        result = ::Ledger::TodayDigest.execute(organization: current_organization)
        render_result(result)
      end
    end
  end
end
