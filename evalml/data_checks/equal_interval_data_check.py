import numpy as np
import woodwork as ww

from evalml.data_checks import (
    DataCheck,
    DataCheckAction,
    DataCheckActionCode,
    DataCheckError,
    DataCheckMessageCode,
    DataCheckWarning,
)
from evalml.utils import infer_feature_types


class EqualIntervalDataCheck(DataCheck):
    """Checks if the datetime column has equally squaced intervals throughout the dataset."""

    def validate(self, X, y):
        """Checks if the target data has equal intervals.

        Arguments:
            X (pd.DataFrame, np.ndarray): Features. Ignored.
            y (pd.Series, np.ndarray): Target data to check for underlying distributions.

        Returns:
            dict (DataCheckError): List with DataCheckErrors if unequal intervals are found in the target data.

        Example:
            >>> from pandas as pd
            >>> X = None
            >>> y = pd.Series(pd.date_range("January 1, 2021", periods=10))
            >>> y[7] = "January 9, 2021"
            >>> target_checdk = EqualIntervalDataCheck()
            >>> assert target_check.validate(X, y) == {"errors": [],\
                                                       "warnings": [{"message": "Target may have a lognormal distribution.",\
                                                                    "data_check_name": "TargetDistributionDataCheck",\
                                                                    "level": "warning",\
                                                                    "code": "TARGET_LOGNORMAL_DISTRIBUTION",\
                                                                    "details": {"shapiro-statistic/pvalue": '0.993/0.0'}}],\
                                                        "actions": [{'code': 'TRANSFORM_TARGET', 'metadata': {'column': None, 'transformation_strategy': 'lognormal', 'is_target': True}}]}
        """
        results = {"warnings": [], "errors": [], "actions": []}

        if y is None:
            results["errors"].append(
                DataCheckError(
                    message="Target is None",
                    data_check_name=self.name,
                    message_code=DataCheckMessageCode.TARGET_IS_NONE,
                    details={},
                ).to_dict()
            )
            return results

        y = infer_feature_types(y)
        allowed_types = [
            ww.logical_types.Integer.type_string,
            ww.logical_types.Double.type_string,
        ]
        is_supported_type = y.ww.logical_type.type_string in allowed_types

        if not is_supported_type:
            results["errors"].append(
                DataCheckError(
                    message="Target is unsupported {} type. Valid Woodwork logical types include: {}".format(
                        y.ww.logical_type.type_string,
                        ", ".join([ltype for ltype in allowed_types]),
                    ),
                    data_check_name=self.name,
                    message_code=DataCheckMessageCode.TARGET_UNSUPPORTED_TYPE,
                    details={"unsupported_type": y.ww.logical_type.type_string},
                ).to_dict()
            )
            return results

        # Check if a normal distribution is detected with p-value above 0.05
        if shapiro(y).pvalue >= 0.05:
            return results

        y_new = y
        if any(y <= 0):
            y_new = y + abs(y.min()) + 1

        y_new = y_new[
            y_new < (y_new.mean() + 3 * round(y.std(), 3))
        ]  # Drop values greater than 3 standard deviations
        shapiro_test_og = shapiro(y_new)
        shapiro_test_log = shapiro(np.log(y_new))

        log_detected = False

        # If the p-value of the log transformed target is greater than or equal to the p-value of the original target
        # with outliers dropped, then it would imply that the log transformed target has more of a normal distribution
        if shapiro_test_log.pvalue >= shapiro_test_og.pvalue:
            log_detected = True

        if log_detected:
            details = {
                "shapiro-statistic/pvalue": f"{round(shapiro_test_og.statistic, 3)}/{round(shapiro_test_og.pvalue, 3)}"
            }
            results["warnings"].append(
                DataCheckWarning(
                    message="Target may have a lognormal distribution.",
                    data_check_name=self.name,
                    message_code=DataCheckMessageCode.TARGET_LOGNORMAL_DISTRIBUTION,
                    details=details,
                ).to_dict()
            )
            results["actions"].append(
                DataCheckAction(
                    DataCheckActionCode.TRANSFORM_TARGET,
                    metadata={
                        "column": None,
                        "is_target": True,
                        "transformation_strategy": "lognormal",
                    },
                ).to_dict()
            )

        return results
