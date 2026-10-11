"""Independent native definition readback and exact L-sheet parameter updates."""

from . import binding
from .documents import rejected
from .jobs import ExecutionFailure


BASE_OPTION_NAMES=('UseDefaultBendRelief','UseReliefRatio','ReliefRatio','ReliefType','ReliefWidth','ReliefDepth')
SHEET_OPTION_NAMES=('AutoReliefType','ReliefRatio','UseAutoRelief')
TEMPLATE_OPTION_NAMES=(*SHEET_OPTION_NAMES,'Thickness','BendRadius','UseMaterialSheetMetalParameters','AllowanceType','KFactor')


class CadSheetParametersReadMixin:
    def _sheet_parameter_template(self,model,target):
        extension=binding.wrap(model.Extension,self._module.IModelDocExtension)
        template=binding.wrap(extension.GetTemplateSheetMetal(),self._module.IFeature)
        member=next(member for member in target.members if member.role=='sheet_folder')
        if (template is None or template.GetTypeName2()!='TemplateSheetMetal'
                or self.identity(template)!=member.identity):
            raise rejected('sheet_parameter_template_unconfirmed','The native template must bind the exact retained sheet folder.')
        data=binding.wrap(template.GetDefinition(),self._module.ISheetMetalFeatureData)
        if data is None:raise rejected('sheet_parameter_template_unconfirmed','The exact template definition is required.')
        allowance=binding.wrap(data.GetCustomBendAllowance(),self._module.ICustomBendAllowance)
        if allowance is None:raise rejected('sheet_parameter_template_unconfirmed','The independent template allowance is required.')
        return template,data,allowance

    def sheet_parameter_options(self,model,target):
        target,_=self.sheet_state_target(model,target.base,target)
        feature=next(member.feature for member in target.members if member.role=='sheet')
        base=binding.wrap(target.base.GetDefinition(),self._module.IBaseFlangeFeatureData)
        sheet=binding.wrap(feature.GetDefinition(),self._module.ISheetMetalFeatureData)
        if base is None or sheet is None:
            raise rejected('sheet_parameter_definition_unavailable','Independent native base and sheet definitions are required.')
        _,data,allowance=self._sheet_parameter_template(model,target)
        gauge=data.GetUseGaugeTable()
        if not isinstance(gauge,(list,tuple)) or len(gauge)!=3:
            raise rejected('sheet_parameter_gauge_unconfirmed','The native gauge-table result/code/flag/path must be complete.')
        return dict(base={name:getattr(base,name) for name in BASE_OPTION_NAMES},
            sheet={name:getattr(sheet,name) for name in SHEET_OPTION_NAMES},
            template={**{name:getattr(data,name) for name in TEMPLATE_OPTION_NAMES if name not in ('AllowanceType','KFactor')},
                'AllowanceType':allowance.Type,'KFactor':allowance.KFactor},
            gauge=dict(result_code=gauge[0],enabled=gauge[1],file_name=gauge[2]))


class CadSheetParametersMixin(CadSheetParametersReadMixin):
    """Update only the exact retained template; unknown COM outcomes stay unresolved."""
    def sheet_modify_parameters(self,model,target,definition):
        target,_=self.sheet_state_target(model,target.base,target)
        template,data,allowance=self._sheet_parameter_template(model,target)
        values=(definition.thickness_mm/1000.,definition.bend_radius_mm/1000.,definition.k_factor)
        current=(data.Thickness,data.BendRadius,allowance.KFactor)
        if current==values:return False
        access_started=False;modified=False;unresolved=False
        try:
            self._sheet_state_target_current(model,target)
            access_started=True
            access=data.AccessSelections(model,None)
            if access is not True:
                raise rejected('sheet_parameter_access_failed','Native access to the exact template definition was not confirmed.')
            # AccessSelections intentionally rolls back; do not enumerate the
            # disappearing body/features or adopt new refs until roll-forward.
            self._sheet_state_target_current(model,target)
            data.Thickness=values[0];data.BendRadius=values[1]
            allowance.Type=2;allowance.KFactor=values[2];data.SetCustomBendAllowance(allowance)
            if (data.Thickness,data.BendRadius,allowance.Type,allowance.KFactor)!=(values[0],values[1],2,values[2]):
                raise rejected('sheet_parameter_stage_failed','The exact three requested definition values were not retained.')
            self._sheet_state_target_current(model,target)
            if template.ModifyDefinition(data,model,None) is not True:
                raise rejected('sheet_parameter_modify_failed','The exact template definition update was not confirmed.')
            modified=True
        except ExecutionFailure:
            raise
        except Exception as error:
            unresolved=True
            raise ExecutionFailure('sheet_parameter_native_unconfirmed',
                'A native definition call failed with an unconfirmed outcome.',uncertain=True) from error
        finally:
            if access_started and not modified and not unresolved:
                try:
                    self._sheet_state_target_current(model,target)
                    if data.ReleaseSelectionAccess() is not None:raise RuntimeError('Unexpected native release return.')
                except BaseException as error:
                    raise ExecutionFailure('sheet_parameter_access_unresolved',
                        'Release of the exact owned template selection access is unconfirmed.',uncertain=True) from error
        self._sheet_state_target_current(model,target)
        if model.ForceRebuild3(False) is not True:
            raise rejected('sheet_parameter_rebuild_failed','Native parameter rebuilding was not confirmed.')
        return True
