# frozen_string_literal: true

module Api
  module V1
    class SyncController < Api::V1::BaseController
      def show
        result = ::Sync::Status.execute(organization: current_organization)
        render_result(result)
      end

      def create
        result = ::Sync::Start.execute(organization: current_organization)
        render_result(result, status: :accepted)
      end
    end
  end
end
