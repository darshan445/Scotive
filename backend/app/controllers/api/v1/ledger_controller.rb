# frozen_string_literal: true

module Api
  module V1
    class LedgerController < Api::V1::BaseController
      def show
        result = ::Ledger::Build.execute(organization: current_organization)
        render_result(result)
      end
    end
  end
end
