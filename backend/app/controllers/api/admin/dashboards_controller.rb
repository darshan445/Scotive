# frozen_string_literal: true

module Api
  module Admin
    class DashboardsController < Api::Admin::BaseController
      def show
        result = ::Admin::Dashboard.execute
        render_result(result)
      end
    end
  end
end
